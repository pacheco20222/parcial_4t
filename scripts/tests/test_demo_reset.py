"""Exercise reset control flow with a Docker double; never contacts Docker."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class DemoResetTests(unittest.TestCase):
    def run_reset(self, *args, answer="", fail=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docker = root / "docker"
            docker.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
with Path(os.environ["CALL_LOG"]).open("a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "stdin": sys.stdin.read()}) + "\\n")
if os.environ.get("FAIL_DOCKER"):
    sys.exit(9)
''')
            docker.chmod(0o755)
            log = root / "calls"
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}", CALL_LOG=str(log))
            if fail:
                env["FAIL_DOCKER"] = "1"
            result = subprocess.run(["bash", str(ROOT / "scripts/demo-reset.sh"), *args],
                                    input=answer, text=True, capture_output=True, env=env)
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            return result, calls

    def test_confirmation_required_before_any_docker_call(self):
        for answer in ["", "yes\n", "reset\n"]:
            result, calls = self.run_reset(answer=answer)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(calls, [])

    def test_reset_scope_and_cache_scan(self):
        for args, answer in [(('--yes',), ''), ((), 'RESET\n')]:
            result, calls = self.run_reset(*args, answer=answer)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(calls), 3)
            self.assertEqual(calls[0]['args'], ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'flood', '-v', 'ON_ERROR_STOP=1'])
            sql = calls[0]['stdin']
            for table in ['ops.alert', 'ops.work_order', 'ops.citizen_report', 'ops.processed_event', 'ops.outbox_message']:
                self.assertIn(table, sql)
            self.assertIn("UPDATE telemetry.monitoring_point SET status = 'Normal'", sql)
            self.assertIn('ALTER SEQUENCE ops.work_order_seq RESTART WITH 1', sql)
            self.assertIn('ALTER SEQUENCE ops.citizen_report_seq RESTART WITH 1', sql)
            for protected in ['audit_log', 'raw_reading', 'clean_reading', 'users', 'crew']:
                self.assertNotIn(protected, sql)
            redis = calls[1]['stdin']
            self.assertIn('REDISCLI_AUTH', redis)
            self.assertIn('/run/secrets/redis_password', redis)
            self.assertIn('SCAN', redis)
            self.assertIn('cache:kpis:*', redis)
            self.assertNotIn('KEYS', redis)
            self.assertNotIn('stream:point-status', redis)
            self.assertNotIn(' -a ', redis)
            self.assertEqual(calls[2]['args'], ['compose', 'restart', 'simulator', 'citizen-bot'])

    def test_failure_stops_before_restart(self):
        result, calls = self.run_reset('--yes', fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)

    def test_unknown_arguments_rejected(self):
        result, calls = self.run_reset('--yes', 'extra')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])


class RedisResetTests(unittest.TestCase):
    def test_scan_pages_delete_only_kpis_with_env_auth(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = root / 'password'
            secret.write_text('test-only-password')
            log = root / 'commands'
            cli = root / 'redis-cli'
            cli.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
assert os.environ['REDISCLI_AUTH'] == 'test-only-password'
assert 'test-only-password' not in sys.argv
args = sys.argv[1:]
with Path(os.environ['CLI_LOG']).open('a') as log:
    log.write(json.dumps(args) + '\\n')
if args[1] == 'SCAN':
    assert args[3:] == ['MATCH', 'cache:kpis:*', 'COUNT', '100']
    print('21\\ncache:kpis:ops' if args[2] == '0' else '0\\ncache:kpis:telemetry')
elif args[1] == 'DEL':
    assert args[2].startswith('cache:kpis:')
    print('1')
else:
    sys.exit(2)
''')
            cli.chmod(0o755)
            script = (ROOT / 'scripts/demo-reset.sh').read_text().split("<<'REDIS'\n", 1)[1].split('\nREDIS', 1)[0]
            script = script.replace('/run/secrets/redis_password', str(secret))
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}", CLI_LOG=str(log))
            result = subprocess.run(['sh', '-eu'], input=script, text=True, capture_output=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual([call[2] for call in calls if call[1] == 'DEL'],
                             ['cache:kpis:ops', 'cache:kpis:telemetry'])
            self.assertEqual(sum(call[1] == 'SCAN' for call in calls), 2)
            self.assertNotIn('test-only-password', result.stdout + result.stderr)

"""Offline infrastructure checks. Docker/Redis doubles do not prove live behavior."""
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECRET_NAMES = {
    "postgres_password", "telemetry_db_password", "ops_db_password", "redis_password",
    "mqtt_telemetry_password", "mqtt_devices.json", "mosquitto_passwd", "ca.crt",
    "ca.key", "mqtt_server.crt", "mqtt_server.key", "jwt_private.pem", "jwt_public.pem",
    "seed_admin_password", "seed_supervisor_password", "seed_operator_password",
    "grafana_admin_password",
}


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        shutil.copy(ROOT / "scripts/bootstrap.sh", self.root / "scripts/bootstrap.sh")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        docker = bin_dir / "docker"
        docker.write_text('''#!/usr/bin/env python3
import hashlib, os, pathlib, sys
if os.environ.get("FAIL_DOCKER"):
    sys.exit(17)
args = sys.argv[1:]
assert "--network" in args and args[args.index("--network") + 1] == "none"
assert args[-3:] == ["eclipse-mosquitto:2.0.22", "-U", "/work/mosquitto_passwd"]
mount = args[args.index("--mount") + 1]
work = pathlib.Path(mount.split("src=", 1)[1].rsplit(",dst=", 1)[0])
f = work / "mosquitto_passwd"
lines = []
for line in f.read_text().splitlines():
    user, password = line.split(":", 1)
    lines.append(user + ":TEST-ONLY-" + hashlib.sha256(password.encode()).hexdigest())
f.write_text("\\n".join(lines) + "\\n")
''')
        docker.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")

    def bootstrap(self, *args, success=True):
        result = subprocess.run(
            ["bash", str(self.root / "scripts/bootstrap.sh"), *args],
            env=self.env, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return result

    def snapshot(self):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (self.root / "secrets").iterdir() if p.is_file()}

    def openssl(self, *args):
        return subprocess.check_output(["openssl", *args], text=True, stderr=subprocess.DEVNULL)

    def test_generation_idempotence_recovery_and_force(self):
        result = self.bootstrap()
        secrets = self.root / "secrets"
        self.assertEqual(set(self.snapshot()), SECRET_NAMES)
        self.assertEqual(stat.S_IMODE(secrets.stat().st_mode), 0o700)
        for path in secrets.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        for role in ["admin", "supervisor", "operator"]:
            password = (secrets / f"seed_{role}_password").read_text().strip()
            for pattern in [r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]"]:
                self.assertRegex(password, pattern)
        devices = json.loads((secrets / "mqtt_devices.json").read_text())
        self.assertEqual(set(devices), {f"DEV-P0{i}-A" for i in range(1, 6)})
        self.assertEqual(len(set(devices.values())), 5)
        for password in devices.values():
            self.assertNotIn(password, result.stdout + result.stderr)
            self.assertNotIn(password, (secrets / "mosquitto_passwd").read_text())
        passwd_users = {line.split(":")[0] for line in
                        (secrets / "mosquitto_passwd").read_text().splitlines()}
        self.assertEqual(passwd_users, set(devices) | {"svc-telemetry"})
        cert = self.openssl("x509", "-in", str(secrets / "mqtt_server.crt"), "-text", "-noout")
        self.assertIn("DNS:mosquitto, DNS:localhost", cert)
        self.assertIn("2048 bit", cert)
        self.openssl("verify", "-CAfile", str(secrets / "ca.crt"), str(secrets / "mqtt_server.crt"))
        private = secrets / "jwt_private.pem"
        self.assertTrue(private.read_text().startswith("-----BEGIN PRIVATE KEY-----"))
        derived = self.openssl("pkey", "-in", str(private), "-pubout")
        self.assertEqual(derived, (secrets / "jwt_public.pem").read_text())
        before = self.snapshot()
        self.bootstrap()
        self.assertEqual(before, self.snapshot())
        (secrets / "jwt_public.pem").unlink()
        (secrets / "mosquitto_passwd").unlink()
        self.bootstrap()
        self.assertEqual(before, self.snapshot())
        (secrets / "mqtt_telemetry_password").unlink()
        self.bootstrap()
        recovered = self.snapshot()
        self.assertNotEqual(before["mosquitto_passwd"], recovered["mosquitto_passwd"])
        self.assertEqual(before["mqtt_devices.json"], recovered["mqtt_devices.json"])
        self.bootstrap("--force")
        after = self.snapshot()
        self.assertTrue(all(before[name] != after[name] for name in SECRET_NAMES))
        self.assertFalse(list(secrets.glob(".bootstrap.*")))

    def test_invalid_arguments_do_not_create_secrets(self):
        self.bootstrap("--unknown", success=False)
        self.bootstrap("--force", "extra", success=False)
        self.assertFalse((self.root / "secrets").exists())

    def test_docker_failure_is_visible_and_cleans_plaintext(self):
        self.env["FAIL_DOCKER"] = "1"
        self.bootstrap(success=False)
        self.assertFalse((self.root / "secrets/mosquitto_passwd").exists())
        self.assertFalse(list((self.root / "secrets").glob(".bootstrap.*")))

    def test_refuses_symlink_directory(self):
        target = self.root / "other"
        target.mkdir()
        (self.root / "secrets").symlink_to(target)
        self.bootstrap(success=False)
        self.assertEqual(list(target.iterdir()), [])


class RedisTests(unittest.TestCase):
    def run_wrapper(self, password):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "password").write_text(password)
            (root / "base.conf").write_text((ROOT / "infra/redis/redis.conf").read_text())
            wrapper = (ROOT / "infra/redis/start.sh").read_text()
            wrapper = wrapper.replace("/run/secrets/redis_password", str(root / "password"))
            wrapper = wrapper.replace("/usr/local/etc/redis/redis.conf", str(root / "base.conf"))
            wrapper = wrapper.replace("/tmp/redis.conf", str(root / "generated.conf"))
            server = root / "redis-server"
            server.write_text('#!/bin/sh\nexit 0\n')
            server.chmod(0o755)
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}")
            result = subprocess.run(["sh", "-c", wrapper], env=env, capture_output=True, text=True, check=False)
            generated = root / "generated.conf"
            return result, generated.read_text() if generated.exists() else None

    def test_injects_password_and_keeps_hardening(self):
        result, config = self.run_wrapper("0123abcdef\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("requirepass 0123abcdef\n", config)
        self.assertIn("protected-mode yes", config)
        self.assertIn("appendonly yes", config)
        for command in ["FLUSHALL", "FLUSHDB", "CONFIG", "KEYS"]:
            self.assertIn(f'rename-command {command} ""', config)
        self.assertNotIn("0123abcdef", result.stdout + result.stderr)

    def test_rejects_empty_and_config_injection(self):
        for password in ["", 'abc\nprotected-mode no', 'abc"', "abc def"]:
            with self.subTest(password=password):
                result, config = self.run_wrapper(password)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(config)


if __name__ == "__main__":
    unittest.main()

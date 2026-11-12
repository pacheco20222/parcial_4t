"""Offline configuration checks; not a replacement for Loki/Grafana runtime validation."""
import ipaddress
import json
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def load(path):
    return yaml.safe_load(path.read_text())


def walk_stages(stages):
    for stage in stages:
        yield stage
        if 'match' in stage:
            yield from walk_stages(stage['match']['stages'])


class ObservabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = load(REPO / 'docker-compose.yml')
        cls.promtail = load(ROOT / 'promtail.yaml')
        cls.stages = list(walk_stages(cls.promtail['scrape_configs'][0]['pipeline_stages']))
        cls.rules = load(ROOT / 'grafana/provisioning/alerting/rules.yaml')['groups'][0]

    def test_all_documents_parse_and_are_nonempty(self):
        for path in ROOT.rglob('*.yaml'):
            with self.subTest(path=path):
                self.assertIsInstance(load(path), dict)
        dashboard = json.loads((ROOT / 'grafana/dashboards/soc.json').read_text())
        self.assertEqual(dashboard['title'], 'SOC — Flood Platform')
        self.assertGreaterEqual(len(dashboard['panels']), 7)
        self.assertTrue(all(p['datasource']['uid'] == 'loki' for p in dashboard['panels']))

    def test_services_are_private_hardened_and_pinned(self):
        for name in ('loki', 'promtail', 'grafana'):
            with self.subTest(service=name):
                service = self.compose['services'][name]
                self.assertRegex(service['image'], r':\d+\.\d+\.\d+$')
                self.assertEqual(service['networks'], ['mon_net'])
                self.assertNotIn('ports', service)
                self.assertTrue(service['read_only'])
                self.assertIn('ALL', service['cap_drop'])
                self.assertIn('no-new-privileges:true', service['security_opt'])
                self.assertIn('mem_limit', service)
                self.assertIn('healthcheck', service)
                for mount in service['volumes']:
                    if mount.startswith('./'):
                        self.assertTrue(mount.endswith(':ro'))
                        self.assertTrue((REPO / mount.split(':')[0]).exists())
        self.assertNotEqual(self.compose['services']['grafana']['user'].split(':')[0], '0')
        self.assertNotEqual(self.compose['services']['loki']['user'].split(':')[0], '0')
        self.assertEqual(self.compose['services']['promtail']['user'], '0:0')

    def test_volume_declarations_and_secret_path(self):
        for name in ('loki', 'promtail', 'grafana'):
            for mount in self.compose['services'][name]['volumes']:
                source = mount.split(':')[0]
                if not source.startswith(('.', '/')):
                    self.assertIn(source, self.compose['volumes'])
        env = self.compose['services']['grafana']['environment']
        self.assertEqual(env['GF_SECURITY_ADMIN_PASSWORD__FILE'], '/run/secrets/grafana_admin_password')
        self.assertNotIn('GF_SECURITY_ADMIN_PASSWORD', env)
        self.assertEqual(env['GF_SERVER_ROOT_URL'], '%(protocol)s://%(domain)s/soc/')
        self.assertEqual(env['GF_SERVER_SERVE_FROM_SUB_PATH'], 'true')
        self.assertEqual(env['GF_SECURITY_COOKIE_SECURE'], 'true')
        self.assertEqual(env['GF_AUTH_ANONYMOUS_ENABLED'], 'false')
        self.assertEqual(env['GF_USERS_ALLOW_SIGN_UP'], 'false')

    def test_retention_and_filesystem_storage(self):
        loki = load(ROOT / 'loki.yaml')
        self.assertFalse(loki['auth_enabled'])
        self.assertEqual(loki['limits_config']['retention_period'], '168h')
        self.assertTrue(loki['compactor']['retention_enabled'])
        self.assertEqual(loki['schema_config']['configs'][0]['object_store'], 'filesystem')
        self.assertEqual(loki['schema_config']['configs'][0]['index']['period'], '24h')

    def test_mosquitto_success_actual_format_ipv4_and_ipv6(self):
        pattern = next(s['regex']['expression'] for s in self.stages
                       if 'regex' in s and 'New client connected' in s['regex']['expression'])
        for ip in ('172.30.10.12', '172.30.20.12', '2001:db8::1'):
            line = f"2026-11-12T07:40:00Z: New client connected from {ip}:49152 as sim-DEV-P01-A-abc (p2, c1, k60, u'DEV-P01-A')."
            match = re.search(pattern, line)
            self.assertIsNotNone(match)
            self.assertEqual(match['client_ip'], ip)
            self.assertEqual(match['user'], 'DEV-P01-A')
            self.assertEqual(ipaddress.ip_address(ip) in ipaddress.ip_network('172.30.10.0/24'), ip.startswith('172.30.10.'))

    def test_mosquitto_failure_missing_ip_never_invents_identity(self):
        branch = next(s['match'] for s in self.stages if 'match' in s and 'not authori' in s['match']['selector'])
        expression = branch['stages'][0]['regex']['expression']
        for client_id in ('sim-DEV-P01-A-683e72eb14', 'atk-DEV-P01-A-abc', '<unknown>', 'arbitrary-id'):
            line = f'2026-11-12T07:51:44Z: Client {client_id} disconnected, not authorised.'
            with self.subTest(client_id=client_id):
                match = re.search(expression, line)
                self.assertIsNotNone(match)
                self.assertEqual(match.groupdict(), {'client_id': client_id})
        for line in (
            '2026-11-12T07:51:44Z: New connection from 172.30.10.5:41234 on port 8883.',
            'Client <unknown> disconnected: Protocol error.',
        ):
            self.assertIsNone(re.search(expression, line))
        self.assertEqual(branch['stages'][1]['template']['template'], 'mqtt.auth_failed')
        self.assertFalse(any(s.get('template', {}).get('source') == 'user' for s in branch['stages']))
        fallback = next(s for s in self.stages if s.get('template', {}).get('source') == 'client_ip')
        self.assertIn('unknown', fallback['template']['template'])
        output = next(s['template']['template'] for s in self.stages
                      if s.get('template', {}).get('source') == 'normalized')
        self.assertIn('"client_id"', output)

    def test_mqtt_bruteforce_counts_broker_wide_over_60_seconds(self):
        rule = self.rules['rules'][1]
        self.assertEqual(rule['data'][0]['model']['expr'],
                         'sum(count_over_time({service="mosquitto",event="mqtt.auth_failed"}[1m]))')
        self.assertEqual(rule['data'][2]['model']['conditions'][0]['evaluator'],
                         {'type': 'gt', 'params': [4]})

    def test_mosquitto_acl_actual_format(self):
        expression = next(s['regex']['expression'] for s in self.stages
                          if 'regex' in s and 'Denied PUBLISH' in s['regex']['expression'])
        match = re.search(expression, "Denied PUBLISH from sim-DEV-P02-A-abc (d0, q1, r0, m1, 'merida/flood/P01/DEV-P01-A/telemetry', ... (233 bytes))")
        self.assertEqual(match['client_id'], 'sim-DEV-P02-A-abc')
        self.assertEqual(match['path'], 'merida/flood/P01/DEV-P01-A/telemetry')

    def test_json_flat_state_and_scope_expressions(self):
        expressions = next(s['json']['expressions'] for s in self.stages
                           if 'json' in s and 'event' in s['json']['expressions'])
        self.assertEqual(expressions['event'], 'event || State.event || Scopes[0].event')
        for name in ('client_ip', 'user', 'device_id'):
            self.assertIn(f'State.{name}', expressions[name])
            self.assertIn(f'Scopes[0].{name}', expressions[name])

    def test_safe_output_and_low_cardinality_labels(self):
        all_templates = [s['template'] for s in self.stages if 'template' in s]
        output = next(t['template'] for t in all_templates if t['source'] == 'normalized')
        self.assertIn('toJson', output)
        for unsafe in ('password', 'cookie', 'authorization', 'Message', 'headers', 'uri'):
            self.assertNotIn('"' + unsafe + '"', output)
        for s in self.stages:
            if 'labels' in s:
                self.assertLessEqual(set(s['labels']), {'event', 'level'})
        expression = next(s['regex']['expression'] for s in self.stages if s.get('regex', {}).get('source') == 'uri')
        self.assertEqual(re.search(expression, '/api/ops/auth/me?token=do-not-log')['path'], '/api/ops/auth/me')
        self.assertEqual(self.promtail['scrape_configs'][0]['pipeline_stages'][-1], {'output': {'source': 'normalized'}})

    def test_caddy_startup_logs_are_not_counted_as_access(self):
        branch = next(s['match'] for s in self.stages
                      if s.get('match', {}).get('selector') == '{service="caddy"}')
        event_template = branch['stages'][-1]['template']['template']
        self.assertEqual(event_template, '{{ if .uri }}http.access{{ else }}service.log{{ end }}')
        timestamps = [s['timestamp'] for s in branch['stages'] if 'timestamp' in s]
        self.assertEqual(timestamps[0]['format'], 'Unix')

    def test_discovery_is_project_scoped_and_socket_readonly(self):
        scrape = self.promtail['scrape_configs'][0]
        self.assertIn('com.docker.compose.project=merida-flood', scrape['docker_sd_configs'][0]['filters'][0]['values'])
        self.assertIn('/var/run/docker.sock:/var/run/docker.sock:ro', self.compose['services']['promtail']['volumes'])

    def test_all_alerts_have_correct_thresholds_actions_and_wiring(self):
        self.assertEqual(self.rules['interval'], '30s')
        thresholds = [1, 5, 1, 1, 1, 10, 1]
        self.assertEqual(len(self.rules['rules']), 7)
        for i, rule in enumerate(self.rules['rules'], 1):
            with self.subTest(rule=rule['uid']):
                self.assertEqual(rule['labels']['rule_id'], f'SR-{i:02d}')
                self.assertIn(rule['labels']['severity'], ('critical', 'high', 'medium'))
                self.assertEqual(rule['condition'], 'C')
                self.assertEqual(rule['for'], '0s')
                self.assertEqual(rule['noDataState'], 'OK')
                self.assertEqual(rule['execErrState'], 'Error')
                a, b, c = rule['data']
                self.assertEqual(a['datasourceUid'], 'loki')
                self.assertEqual(b['model']['expression'], 'A')
                self.assertEqual(b['model']['settings'], {'mode': 'replaceNN', 'replaceWithValue': 0})
                self.assertEqual(c['model']['expression'], 'B')
                self.assertEqual(c['model']['conditions'][0]['evaluator'], {'type': 'gt', 'params': [thresholds[i-1]-1]})
                for name in ('summary', 'description', 'mitre_attack', 'response_action'):
                    self.assertTrue(rule['annotations'][name])

    def test_all_notifications_muted_with_loopback_placeholder(self):
        c = load(ROOT / 'grafana/provisioning/alerting/contact-points.yaml')
        self.assertEqual(c['contactPoints'][0]['name'], 'soc-alerts')
        self.assertEqual(c['contactPoints'][0]['receivers'][0]['settings']['url'], 'http://127.0.0.1:9099/disabled-soc-webhook')
        self.assertEqual(c['policies'][0]['routes'][0]['mute_time_intervals'], ['soc-delivery-disabled'])
        self.assertEqual(c['muteTimes'][0]['time_intervals'][0]['times'], [{'start_time': '00:00', 'end_time': '24:00'}])

    def test_merida_rule_uses_event_time_not_evaluation_time(self):
        expression = self.rules['rules'][6]['data'][0]['model']['expr']
        self.assertIn('__timestamp__', expression)
        self.assertIn('utc_hour >= 5 and utc_hour < 12', expression)
        self.assertIn('account_age_seconds < 86400', expression)
        for utc_hour in range(24):
            self.assertEqual(5 <= utc_hour < 12, not (6 <= (utc_hour - 6) % 24 < 23))

    def test_caddy_route_keeps_soc_prefix(self):
        caddy = (REPO / 'infra/caddy/Caddyfile').read_text()
        self.assertRegex(caddy, r'handle /soc/\*\s*\{\s*reverse_proxy grafana:3000')
        self.assertNotIn('handle_path /soc/', caddy)

    def test_docs_queries_match_provisioned_queries(self):
        docs = (REPO / 'docs/siem-rules.md').read_text()
        for rule in self.rules['rules']:
            self.assertIn(rule['data'][0]['model']['expr'], docs)


if __name__ == '__main__':
    unittest.main()

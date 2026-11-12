"""Static contract checks; no Docker calls or external services."""
import re
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipIf(yaml is None, "Use telemetry's existing venv for PyYAML")
class ComposeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
        cls.services = cls.compose["services"]

    def test_network_membership_and_segmentation(self):
        expected = {
            "caddy": {"edge_net", "app_net", "mon_net"},
            "postgres": {"data_net"}, "redis": {"app_net"},
            "mosquitto": {"ot_net", "idmz_net"}, "simulator": {"ot_net"},
            "telemetry-service": {"app_net", "data_net", "idmz_net"},
            "ops-service": {"app_net", "data_net"},
            "attack-sim": {"ot_net", "idmz_net"},
            "loki": {"mon_net"}, "promtail": {"mon_net"}, "grafana": {"mon_net"},
        }
        self.assertEqual(set(self.services), set(expected))
        for name, networks in expected.items():
            self.assertEqual(set(self.services[name]["networks"]), networks)
        for name, octet in [("edge_net", 0), ("ot_net", 10), ("idmz_net", 20),
                            ("app_net", 30), ("data_net", 40), ("mon_net", 50)]:
            config = self.compose["networks"][name]
            self.assertEqual(config["ipam"]["config"][0]["subnet"], f"172.30.{octet}.0/24")
            self.assertEqual(config.get("internal", False), name in {"ot_net", "idmz_net", "data_net"})
        self.assertEqual(self.services["attack-sim"]["environment"]["MQTT_HOST"], "mosquitto")
        self.assertIn("mosquitto:172.30.20.10", self.services["attack-sim"]["extra_hosts"])
        self.assertEqual(self.services["mosquitto"]["networks"]["idmz_net"]["ipv4_address"], "172.30.20.10")

    def test_only_gateway_publishes_and_all_services_hardened(self):
        for name, config in self.services.items():
            self.assertEqual(bool(config.get("ports")), name == "caddy")
            if name != "promtail":  # documented exception: reads the root-owned Docker socket
                self.assertNotEqual(str(config["user"]).split(":")[0], "0")
            self.assertTrue(config["read_only"])
            self.assertIn("ALL", config["cap_drop"])
            self.assertIn("no-new-privileges:true", config["security_opt"])
            self.assertEqual(config["restart"], "unless-stopped")
            self.assertIn("mem_limit", config)
            self.assertIn("test", config["healthcheck"])
            for dependency in config.get("depends_on", {}).values():
                self.assertEqual(dependency["condition"], "service_healthy")
            if "image" in config:
                self.assertRegex(config["image"], r":\d+\.\d+\.\d+(?:-|$)")
        self.assertEqual(self.services["attack-sim"]["profiles"], ["demo"])
        self.assertEqual(self.services["attack-sim"]["environment"]["ATTACK_SIM_CONFIRM"], "lab")

    def test_private_keys_and_passwords_only_mounted_where_needed(self):
        declared = self.compose["secrets"]
        for service, config in self.services.items():
            mounted = set(config.get("secrets", []))
            self.assertLessEqual(mounted, set(declared))
            self.assertNotIn("ca.key", mounted)
            self.assertEqual("jwt_private.pem" in mounted, service == "ops-service")
            self.assertEqual("postgres_password" in mounted, service == "postgres")
            for key, value in config.get("environment", {}).items():
                if key.endswith(("_FILE", "File")):
                    self.assertTrue(value.startswith("/run/secrets/"), key)
                    self.assertIn(value.removeprefix("/run/secrets/"), mounted, key)
                if "password" in key.lower():
                    self.assertTrue(key.endswith(("_FILE", "File")), key)
        for name, config in declared.items():
            self.assertEqual(config["file"], f"./secrets/{name}")

    def test_exact_service_environment_names(self):
        required = {
            "telemetry-service": "DATABASE_HOST DATABASE_NAME DATABASE_USER DATABASE_PASSWORD_FILE REDIS_HOST REDIS_PASSWORD_FILE MQTT_HOST MQTT_PORT MQTT_USERNAME MQTT_PASSWORD_FILE MQTT_CA_FILE JWT_PUBLIC_KEY_FILE OPEN_METEO_ENABLED ENVIRONMENT",
            "ops-service": "Database__Host Database__Name Database__User Database__PasswordFile Redis__Host Redis__PasswordFile Jwt__PrivateKeyFile Jwt__PublicKeyFile Seed__AdminPasswordFile Seed__SupervisorPasswordFile Seed__OperatorPasswordFile Security__EnforceMfa",
            "simulator": "MQTT_HOST MQTT_PORT MQTT_CA_FILE MQTT_DEVICES_FILE SCENARIO INTERVAL_SECONDS",
        }
        env_example = (ROOT / ".env.example").read_text()
        for service, names in required.items():
            for name in names.split():
                self.assertIn(name, self.services[service]["environment"])
                self.assertIn(name + "=", env_example)

    def test_mqtt_listener_and_acl_are_least_privilege(self):
        conf = (ROOT / "infra/mosquitto/mosquitto.conf").read_text()
        self.assertEqual(re.findall(r"^listener (.+)$", conf, re.MULTILINE), ["8883"])
        self.assertIn("allow_anonymous false", conf)
        self.assertIn("require_certificate false", conf)
        acl = (ROOT / "infra/mosquitto/acl").read_text()
        blocks = {}
        user = None
        for line in acl.splitlines():
            if line.startswith("user "):
                user = line[5:]
                blocks[user] = []
            elif line.startswith("topic "):
                blocks[user].append(line[6:])
        self.assertEqual(blocks.pop("svc-telemetry"), ["read merida/flood/+/+/telemetry"])
        self.assertEqual(len(blocks), 5)
        for i in range(1, 6):
            user = f"DEV-P0{i}-A"
            self.assertEqual(blocks[user], [f"write merida/flood/P0{i}/{user}/telemetry"])

    def test_gateway_routes_headers_and_body_limit(self):
        conf = (ROOT / "infra/caddy/Caddyfile").read_text()
        self.assertIn("handle_path /api/telemetry/*", conf)
        self.assertIn("handle_path /api/ops/*", conf)
        self.assertIn("handle /hubs/*", conf)
        self.assertIn("handle /soc/*", conf)
        self.assertNotIn("handle_path /hubs", conf)
        self.assertNotIn("handle_path /soc", conf)
        for text in ["tls internal", "max_size 1MB", "format json", "output stdout",
                     "Strict-Transport-Security", "frame-ancestors 'none'", "-Server",
                     "X-Content-Type-Options nosniff", "Permissions-Policy"]:
            self.assertIn(text, conf)

    def test_database_uses_quoted_variables_and_schema_owners(self):
        script = (ROOT / "infra/postgres/10-init.sh").read_text()
        for role, schema in [("telemetry_svc", "telemetry"), ("ops_svc", "ops")]:
            self.assertIn(f"CREATE SCHEMA {schema} AUTHORIZATION {role}", script)
            self.assertIn(f"ALTER ROLE {role} IN DATABASE flood SET search_path = {schema}", script)
        self.assertIn("REVOKE ALL ON SCHEMA public FROM PUBLIC", script)
        self.assertIn("PASSWORD :'telemetry_password'", script)
        self.assertIn("PASSWORD :'ops_password'", script)
        self.assertNotRegex(script, r"GRANT .* ON SCHEMA (telemetry|ops)")
        # Only exception: telemetry role may USE public (TimescaleDB functions live there).
        self.assertEqual(re.findall(r"GRANT .* ON SCHEMA public TO (\w+)", script), ["telemetry_svc"])
        self.assertIn("--set=ON_ERROR_STOP=1", script)


if __name__ == "__main__":
    unittest.main()

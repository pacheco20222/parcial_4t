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
            "attack-scheduler": {"ot_net", "idmz_net"},
            "login-attacker": {"app_net"},
            "citizen-bot": {"app_net"},
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

    def test_citizen_bot_has_no_secrets_and_uses_simulator_image(self):
        bot = self.services["citizen-bot"]
        self.assertEqual(bot["build"], self.services["simulator"]["build"])
        self.assertEqual(bot["command"], ["python", "-m", "flood_simulator.citizen_bot"])
        self.assertEqual(bot.get("secrets", []), [])
        self.assertEqual(bot["environment"]["CITIZEN_BOT_ENABLED"], "${CITIZEN_BOT_ENABLED:-true}")
        self.assertEqual(bot["environment"]["CITIZEN_BOT_MIN_INTERVAL_SECONDS"], "${CITIZEN_BOT_MIN_INTERVAL_SECONDS:-150}")

    def test_attack_scheduler_is_opt_in_and_matches_one_shot_hardening(self):
        scheduler = self.services["attack-scheduler"]
        one_shot = self.services["attack-sim"]
        self.assertEqual(scheduler["profiles"], ["soc-demo"])
        self.assertEqual(scheduler["command"], ["python", "-m", "flood_simulator.attack_sim", "--schedule"])
        self.assertEqual(scheduler["environment"]["ATTACK_SIM_CONFIRM"], "lab")
        self.assertEqual(scheduler["environment"]["ATTACK_INTERVAL_MINUTES"], "${ATTACK_INTERVAL_MINUTES:-12}")
        for key in ["build", "user", "read_only", "cap_drop", "security_opt", "secrets",
                    "mem_limit", "networks", "extra_hosts", "depends_on", "healthcheck"]:
            self.assertEqual(scheduler[key], one_shot[key], key)
        deploy = (ROOT / "scripts/deploy-vps.sh").read_text()
        self.assertIn("\nCOMPOSE_PROFILES=soc-demo\n", deploy)
        self.assertIn("\nATTACK_INTERVAL_MINUTES=${ATTACK_INTERVAL_MINUTES:-12}\n", deploy)

    def test_attack_workloads_keep_ot_credentials_out_of_app_zone(self):
        mqtt_scenarios = {"bruteforce", "acl_violation", "flood", "spoof",
                          "foreign_network", "implausible_jump"}
        for name in ("attack-sim", "attack-scheduler"):
            service = self.services[name]
            self.assertEqual(set(service["environment"]["ATTACK_SCENARIOS"].split(",")),
                             mqtt_scenarios)
            self.assertEqual(set(service["secrets"]), {"ca.crt", "mqtt_devices.json"})
            self.assertNotIn("ops-service", service["depends_on"])
        login = self.services["login-attacker"]
        self.assertEqual(login["build"], self.services["simulator"]["build"])
        self.assertEqual(login["profiles"], ["soc-demo"])
        self.assertEqual(login["command"], ["python", "-m", "flood_simulator.attack_sim"])
        self.assertEqual(login.get("secrets", []), [])
        self.assertEqual(login.get("volumes", []), [])
        self.assertEqual(login.get("extra_hosts", []), [])
        self.assertEqual(set(login["depends_on"]), {"ops-service"})
        self.assertEqual(login["environment"], {
            "ATTACK_SIM_CONFIRM": "lab", "ATTACK_SCENARIOS": "login_failures",
            "ATTACK_SCENARIO": "${ATTACK_SCENARIO:-all}",
            "LOGIN_ATTACK_INTERVAL_MINUTES": "${LOGIN_ATTACK_INTERVAL_MINUTES:-30}",
            "ATTACK_SCHEDULE": "${ATTACK_SCHEDULE:-on}",
        })
        for service in self.services.values():
            if "mqtt_devices.json" in service.get("secrets", []):
                self.assertNotIn("app_net", service["networks"])

    def test_static_assets_bypass_spa_and_cache_policy(self):
        conf = (ROOT / "infra/caddy/Caddyfile").read_text()
        static = conf.split("handle @static {", 1)[1].split("\n\thandle {", 1)[0]
        self.assertIn("file_server", static)
        self.assertNotIn("try_files", static)
        self.assertNotIn("templates", static)
        for path in ["*.js", "*.css", "*.map", "*.woff2", "/media/*", "/assets/*"]:
            self.assertIn(path, conf.split("handle @static", 1)[0])
        self.assertIn('Cache-Control "public, max-age=31536000, immutable"', static)
        hashed_pattern = re.search(r"path_regexp hashed (.+)", static).group(1)
        for asset in ["/chunk-Z-GpFkFO.js", "/chunk-DN_O2-dD.js", "/main-L4322USE.js",
                      "/media/barlow-latin-600-normal-IMDL24A2.woff"]:
            self.assertIsNotNone(re.fullmatch(hashed_pattern, asset))
        self.assertIsNone(re.fullmatch(hashed_pattern, "/favicon.svg"))
        self.assertIn("file {path}", static)
        self.assertIn("route {", static)  # preserve default -> immutable header override order
        spa = conf.split("\n\thandle {", 1)[1]
        self.assertIn('Cache-Control "no-cache"', spa)
        self.assertIn("try_files {path} /index.html", spa)
        self.assertIn("templates", spa)

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

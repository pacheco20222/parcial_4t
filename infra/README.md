# Local infrastructure

T1 provides isolated networks, file secrets, schema owners, MQTT TLS/ACLs,
password-protected Redis and an HTTPS gateway. Binding names: `docs/contracts.md`.

From repository root (Docker/Compose, OpenSSL and Python 3 required):

```sh
cp .env.example .env
bash scripts/bootstrap.sh
docker compose config -q
docker compose up --build -d
# Confirm healthy services, then open https://localhost:8443
```

Bootstrap uses `docker run --rm eclipse-mosquitto:2.0.22 mosquitto_passwd` (with
an explicit entrypoint) to hash all six MQTT identities. No password is placed
in command arguments. Existing files are preserved; missing dependent public
keys/certificates/password hashes are rebuilt. `--force` rotates all secrets;
stop services first, back up secrets securely, and plan DB/account password
rotation: existing PostgreSQL volumes and seeded accounts are **not** updated
by bootstrap. If hashing fails during rotation, rerun with `--force` before start.

`secrets/` is ignored and mode 0700. Files are 0644 because Compose bind-backed
secrets preserve host permissions and multiple non-root container UIDs need
read access. Directory traversal protects files on the host; each container
receives only its explicit mounts. CA private key never mounts into containers;
JWT private key mounts only in ops. Do not loosen directory permissions.

Compose fixes DB `flood`, users `telemetry_svc`/`ops_svc`; all passwords/keys are
`/run/secrets` file mounts. Host substitutions in `.env.example`:
`SITE_ADDRESS`, `GATEWAY_HTTPS_PORT` (8443), `GATEWAY_HTTP_PORT` (8080),
`ENVIRONMENT` (dev|prod), `OPEN_METEO_ENABLED` (true),
`SECURITY_ENFORCE_MFA` (false), `SCENARIO` (cycle), `INTERVAL_SECONDS` (60;
use 5 for demo). Setting these does not bypass service authentication.

Exact container environment (Compose sets these, `.env` overrides only the
substitutions above):

- Telemetry, port 8000: `DATABASE_HOST`, `DATABASE_NAME`, `DATABASE_USER`,
  `DATABASE_PASSWORD_FILE`, `REDIS_HOST`, `REDIS_PASSWORD_FILE`, `MQTT_HOST`,
  `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD_FILE`, `MQTT_CA_FILE`,
  `JWT_PUBLIC_KEY_FILE`, `OPEN_METEO_ENABLED`, `ENVIRONMENT`.
- Ops, port 8080: `Database__Host`, `Database__Name`, `Database__User`,
  `Database__PasswordFile`, `Redis__Host`, `Redis__PasswordFile`,
  `Jwt__PrivateKeyFile`, `Jwt__PublicKeyFile`, `Seed__AdminPasswordFile`,
  `Seed__SupervisorPasswordFile`, `Seed__OperatorPasswordFile`,
  `Security__EnforceMfa`.
- Simulator: `MQTT_HOST`, `MQTT_PORT`, `MQTT_CA_FILE`, `MQTT_DEVICES_FILE`,
  `SCENARIO`, `INTERVAL_SECONDS`.

Only gateway ports publish. `/api/telemetry/*` → telemetry (prefix removed),
`/api/ops/*` → ops (prefix removed), `/hubs/*` → ops (WebSocket supported,
prefix retained), `/soc/*` → T5 Grafana (prefix retained); other paths serve
placeholder SPA. `/api/telemetry/healthz` checks telemetry. Public health/static
routes intentionally support local monitoring and the future frontend.
Caddy redirects HTTP to the configured external HTTPS port. Its internal CA
persists in `caddydata`; install its root certificate in the local trust store
before browser testing. Do not disable certificate verification in clients.

MQTT accepts TLS only on 8883; devices write only their own contracted telemetry
topics; `svc-telemetry` only reads `merida/flood/+/+/telemetry`. Events remain
owned by services: Redis `stream:point-status`, `events:telemetry`, `events:ops`.
No broker/DB/Redis host ports. Non-internal Docker networks permit egress;
Compose alone does not enforce destination-specific Open-Meteo restrictions.

Demo (own local stack only):

```sh
INTERVAL_SECONDS=5 docker compose up -d simulator
docker compose --profile demo run --rm attack-sim
```

`attack-sim` joins OT and IDMZ; an `extra_hosts` entry maps `mosquitto` to its
fixed IDMZ address (172.30.20.10), ensuring an IDMZ source for SR-01 while
preserving TLS hostname verification against the `mosquitto` certificate SAN. Prefer the one-off command
above; `up` with demo profile applies `unless-stopped` and can repeat attacks.

Validation, no network/Docker needed:

```sh
bash -n scripts/bootstrap.sh
bash -n infra/postgres/10-init.sh
sh -n infra/redis/start.sh
python3 -m unittest discover -s scripts/tests -v
services/telemetry-service/.venv/bin/python -m unittest discover -s scripts/tests -p 'test_compose.py' -v
```

Bootstrap tests use real OpenSSL and a Docker double; Redis startup uses a server
double. Compose tests use existing PyYAML from telemetry's restored environment.
They prove local generation, permissions, idempotence, input rejection and static
configuration invariants, not running images. No new dependencies installed.

Orchestrator integration checks:

- Run `docker compose config -q`, build/start and verify image tags, volume
  ownership and non-root startup. Ops healthcheck needs bash (`aspnet:10.0`
  standard image); telemetry/simulator need `python` on PATH. Align T2–T4 images.
- Init scripts run only on an empty PG volume. Verify service logins, migrations,
  Timescale hypertable creation and cross-schema denial. Revoking public schema
  rights also removes access to extension APIs installed there: coordinate
  explicit narrowly scoped Timescale access if T2 migrations need public APIs;
  no public or cross-schema service grants are added here.
- Broker healthcheck checks the listening socket; simulator checks PID liveness.
  Verify actual authenticated TLS ingestion/ACL rejection and service flow in T7.
- T5 adds Grafana/Loki/Promtail at the Compose marker. Until then `/soc/*` has
  no upstream. Normalize native infrastructure logs as noted in contracts.
- Caddy, Mosquitto, Redis and Postgres configuration validation/runtime remain
  pending; Docker execution prohibited in this agent sandbox.

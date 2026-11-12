# Telemetry Service

FastAPI backend for five fictitious Mérida monitoring points. Owns only PostgreSQL
schema `telemetry`: MQTT validation, raw/clean time series, point status, forecasts
and telemetry KPIs. Missing measurements remain null; suspect readings never
change status or refresh the valid-depth clock.

## Run / test

From this directory, with provisioned PostgreSQL/TimescaleDB, Redis and MQTT:

```sh
export PATH="$PWD/.venv/bin:$PATH"
./entrypoint.sh
# Checks require no external services:
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/mypy src
```

Entrypoint applies Alembic migrations, then starts Uvicorn on port 8000. Infra must
create schema `telemetry`, its owner role and the TimescaleDB extension first.
TimescaleDB is expected in `public`: grant `telemetry_svc` USAGE on that schema
and EXECUTE on the required extension functions (`create_hypertable` for migration,
`time_bucket` for runtime). No rights on `ops` or public application tables needed.
The launcher resolves `caddy` and trusts forwarded headers only from those IPs.
Keep one process/replica: hysteresis timers and ingestion serialization are local.
Restart resets the five-minute downgrade timer conservatively, restores the last
valid reading timestamp from PostgreSQL, and detects stale points within 30 s.

## Configuration / secrets

`pydantic-settings` reads environment variables; passwords never come from direct
environment values. Files are loaded at startup; unreadable/empty credentials,
invalid CA or non-RSA public key fail startup.

- Database: `DATABASE_HOST=postgres`, `DATABASE_PORT=5432`, `DATABASE_NAME=flood`,
  `DATABASE_USER=telemetry_svc`,
  `DATABASE_PASSWORD_FILE=/run/secrets/telemetry_db_password`.
- Redis: `REDIS_HOST=redis`, `REDIS_PORT=6379`,
  `REDIS_PASSWORD_FILE=/run/secrets/redis_password`.
- MQTT: `MQTT_HOST=mosquitto`, `MQTT_PORT=8883`, `MQTT_USERNAME=svc-telemetry`,
  `MQTT_PASSWORD_FILE=/run/secrets/mqtt_telemetry_password`,
  `MQTT_CA_FILE=/run/secrets/ca.crt` (hostname/certificate verification enabled).
- JWT: `JWT_PUBLIC_KEY_FILE=/run/secrets/jwt_public.pem`; RS256,
  issuer `flood-ops`, audience `flood-platform`, cookie `flood_at` or Bearer token.
- `MAX_MSGS_PER_DEVICE_PER_MIN=10`: positive per-device fixed-window limit;
  messages above it emit `telemetry.rate_exceeded` (SR-04) and are dropped before persistence, dedup, cache or publication.
  A 10-second simulator sends 6/min; a 180/min flood exceeds the default.
- `OPEN_METEO_ENABLED=true`, `ENFORCE_MFA=false`, `LOG_LEVEL=INFO`,
  `ENVIRONMENT=dev` for local docs; Compose defaults to `prod` (OpenAPI/docs disabled).

Dockerfile uses locked production dependencies, non-root UID/GID 10001, no build
tools in final stage, and urllib liveness healthcheck. Supports read-only root;
mount secrets read-only and supply `/tmp` tmpfs if infrastructure needs it.

## HTTP / events

Gateway strips `/api/telemetry`; Uvicorn `root_path` carries that prefix.

- `GET /healthz`: public liveness only; `GET /readyz`: DB + Redis readiness.
- `GET /public/points`: public status, last valid depth and age; 60 requests/min/IP.
- Operator+: `GET /points/{id}/readings?from=...&to=...&bucket=5m`
  (aware timestamps, default six hours, maximum seven days; `1m|5m|15m|1h`),
  `GET /kpis` (10-second cache), `GET /points/{id}/forecast` (next 24 hours).
- Supervisor/Admin: `PATCH /points/{id}/thresholds`, JSON
  `{"watchThresholdCm":15,"alertThresholdCm":25}`; `0 < watch < alert <= 150`.
  MFA enforced when configured. Every unsafe method requires
  `X-Requested-With: XMLHttpRequest`.

MQTT subscribes `merida/flood/+/+/telemetry`, TLS/QoS1; checks topic/device ownership,
rate, UUID dedup (24 hours), range and >30 cm jump within 90 seconds. UTC telemetry
more than 60 seconds in the future is rejected; samples at least three minutes
old are suspect. Raw/clean records both retain captured and received timestamps.
Null values remain null in API/events and JSON `null` strings inside Redis hashes.

Redis: `latest:{pointId}` hashes, `events:telemetry` Pub/Sub,
`stream:point-status` (JSON field `data`, approximate MAXLEN 10000, with current
`watchThresholdCm` and `alertThresholdCm`),
`forecast:{pointId}` hashes (one-hour TTL). Status escalates immediately; downgrades
require five minutes, stepping Alert → Watch → Normal. NoData after three minutes
without valid depth, emitted once; first resumed valid depth restores Normal.
Forecast pulls have 10-second HTTP timeouts and three attempts; failures are logged.
All logs are JSON lines with contract SIEM event names and rendered `msg`;
exceptions include `exc` type, message and traceback. SQL bind parameters are hidden;
credentials are omitted.
Telemetry KPIs aggregate quality-ok samples in the last 60 minutes: maximum depth,
`rainLast60minByPoint` = per-point average of rolling five-minute rain × 12,
`rainLast60minMm` = maximum of those point estimates, and age of newest sample.
Rain excludes suspect, old and future samples. All-null rain stays null; points
without quality-ok readings in that window are absent from the map.

## Verification limits

Tests use fake sessions, fakeredis, signed test JWTs and HTTP mock transports.
Orchestrator must build the image and verify migrations/hypertable, least-privilege
DB grants, TLS/ACLs, Caddy source IP trust, read-only container startup and end-to-end
stream delivery. No Docker/network commands were run in the implementation sandbox.
The DB and Redis writes are separate transactions: process termination between
persistence and publication can lose an event. In-process status retries reuse the
same event ID; this Alpha does not provide a durable transactional outbox.

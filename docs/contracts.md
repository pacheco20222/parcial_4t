# Backend Contracts

Single source of truth for cross-service conventions. Every service MUST follow this file. Design rationale: [architecture.md](../architecture.md).

## 1. Repo layout

```text
services/ops-service/        ASP.NET Core (.NET 10) — Ops.sln, src/Ops.Api, tests/Ops.Api.Tests
services/telemetry-service/  FastAPI (Python 3.13, uv) — src/telemetry_service/, tests/, alembic/
simulator/                   Python (uv) — src/flood_simulator/ (simulator + attack_sim)
infra/postgres/              init SQL (schemas, roles, timescale)
infra/mosquitto/             mosquitto.conf, acl
infra/redis/                 redis.conf (password injected at start)
infra/caddy/                 Caddyfile
infra/observability/         loki, promtail, grafana provisioning, alert rules
scripts/bootstrap.sh         generates ./secrets (idempotent)
docker-compose.yml
```

## 2. Secrets (`./secrets/`, git-ignored, created by `scripts/bootstrap.sh`)

| File | Used by |
|---|---|
| `postgres_password` | postgres superuser (init only) |
| `telemetry_db_password`, `ops_db_password` | DB roles `telemetry_svc`, `ops_svc` |
| `redis_password` | redis, both services |
| `mqtt_telemetry_password` | MQTT user `svc-telemetry` |
| `mqtt_devices.json` | `{"DEV-P01-A":"<pw>", ... "DEV-P05-A":"<pw>"}` — simulator |
| `mosquitto_passwd` | hashed passwd file for mosquitto (all identities) |
| `ca.crt`, `ca.key`, `mqtt_server.crt`, `mqtt_server.key` | MQTT TLS (CN/SAN `mosquitto`) |
| `jwt_private.pem` / `jwt_public.pem` | RS256: ops signs, telemetry verifies |
| `seed_admin_password`, `seed_supervisor_password`, `seed_operator_password` | ops seed users |
| `grafana_admin_password` | grafana |

Services read secrets from files mounted at `/run/secrets/<name>` (Docker secrets). Env vars carry **paths**, never secret values.

## 3. Networks (fixed subnets — SIEM rules depend on them)

| Network | Subnet | internal |
|---|---|---|
| `edge_net` | 172.30.0.0/24 | no |
| `ot_net` | 172.30.10.0/24 | yes |
| `idmz_net` | 172.30.20.0/24 | yes |
| `app_net` | 172.30.30.0/24 | no (telemetry egress to Open-Meteo) |
| `data_net` | 172.30.40.0/24 | yes |
| `mon_net` | 172.30.50.0/24 | no |

Membership per architecture.md §5. Gateway host port: `${GATEWAY_HTTPS_PORT:-8443}` → caddy 443.

## 4. PostgreSQL

- DB `flood`, image TimescaleDB (pg17). Init creates extension `timescaledb`, schemas `telemetry` and `ops`, roles `telemetry_svc` (owner of `telemetry`) and `ops_svc` (owner of `ops`). `REVOKE ALL ON SCHEMA public FROM PUBLIC`; neither role has rights on the other schema. Each service runs its own migrations at startup (Alembic / EF Core) inside its own schema, using `search_path` = its schema.
- Telemetry tables: `monitoring_point`, `device`, `raw_reading`, `clean_reading` (hypertable on `captured_at`), `forecast`. Seed P01–P05 (fictitious, `simulated=true`, coords inside Mérida) and devices `DEV-P0n-A`.
- Ops tables: Identity tables, `alert`, `work_order`, `crew`, `citizen_report`, `audit_log`, `refresh_token`, `processed_event`.

## 5. MQTT

- Broker `mosquitto:8883` TLS only (no 1883). Clients verify `ca.crt`.
- Topic: `merida/flood/{pointId}/{deviceId}/telemetry`, QoS 1. No command topics.
- ACL: `DEV-P0n-A` → `write merida/flood/P0n/DEV-P0n-A/telemetry`; `svc-telemetry` → `read merida/flood/+/+/telemetry`.
- Payload (JSON, camelCase): `messageId` (uuid), `deviceId`, `pointId`, `capturedAt` (ISO-8601 UTC), `waterDepthCm` (float|null), `rainMm5min` (float|null), `batteryPct` (int), `fwVersion` (str).

## 6. Redis (password required)

| Key / channel | Payload |
|---|---|
| `stream:point-status` (XADD, field `data` = JSON, MAXLEN ~10000; group `ops`) | `{eventId, type:"point.status_changed", pointId, pointName, zone, previous, current, waterDepthCm, watchThresholdCm, alertThresholdCm, occurredAt}` — `current` ∈ `Normal|Watch|Alert|NoData` |
| `events:telemetry` (PUBLISH) | `{type:"telemetry.reading", pointId, deviceId, capturedAt, waterDepthCm, rainMm5min, qualityFlag, status}` — `qualityFlag` ∈ `ok|suspect` |
| `events:ops` (PUBLISH) | `{type, data}` — `type` ∈ `alert.opened|alert.closed|workorder.created|workorder.updated|report.created|report.updated` |
| `latest:{pointId}` (HASH) | last clean reading fields + `status` + `updatedAt` |
| `dedup:{messageId}` | `SET NX EX 86400` |
| `rl:*`, `cache:kpis:*`, `forecast:{pointId}` | internal per service |

## 7. Auth (ops issues, both verify)

- JWT RS256, `iss=flood-ops`, `aud=flood-platform`, claims `sub`, `email`, `role` ∈ `Operator|Supervisor|Admin`, `amr` (`pwd` or `mfa`), `exp` = 15 min.
- Cookie `flood_at` (HttpOnly, Secure, SameSite=Strict, Path=/). Refresh cookie `flood_rt` (rotating, stored hashed, Path=/api/ops/auth, 7 days).
- SignalR reads the token from the `flood_at` cookie.
- CSRF: every POST/PUT/PATCH/DELETE must carry header `X-Requested-With: XMLHttpRequest`, otherwise 403. Both services enforce it.
- Role hierarchy: Admin ⊃ Supervisor ⊃ Operator.
- MFA: TOTP (ASP.NET Identity authenticator). Login of an MFA-enabled user returns `{mfaRequired:true}` + short-lived `flood_mfa` cookie; `/auth/mfa/verify` completes. Setting `Security__EnforceMfa=true` makes Supervisor/Admin endpoints require `amr=mfa` (default false for local demo).

## 8. Gateway routes (Caddy)

| Path | Upstream | Prefix stripped |
|---|---|---|
| `/api/telemetry/*` | `telemetry-service:8000` | yes |
| `/api/ops/*` | `ops-service:8080` | yes |
| `/hubs/*` | `ops-service:8080` | no |
| `/soc/*` | `grafana:3000` (serve_from_sub_path) | no |
| `/*` | static Angular SPA built into the caddy image (`frontend/`) | — |

## 9. Logging (SIEM input)

JSON lines to stdout: `ts` (ISO UTC), `level`, `service`, `event`, plus context (`client_ip`, `user`, `device_id`, `point_id`, `path`, `status`). Never log secrets, passwords, tokens or cookies.

Event names: telemetry → `telemetry.ingested`, `telemetry.validation_failed`, `telemetry.duplicate`, `telemetry.suspect_reading`, `telemetry.rate_exceeded`, `telemetry.topic_mismatch`, `point.status_changed`, `auth.jwt_rejected`, `csrf.rejected`. ops → `auth.login_success`, `auth.login_failed`, `auth.lockout`, `auth.mfa_failed`, `auth.jwt_rejected`, `csrf.rejected`, `ratelimit.hit`, `audit.<action>` (e.g. `audit.threshold_change` is telemetry-side, `audit.workorder_cancel` ops-side), `stream.event_processed`.

## 10. Status / ERP rules

- Status machine and thresholds: architecture.md §7 (Watch ≥ watch threshold, Alert ≥ alert threshold, 5 min hysteresis down, NoData after 3 min silence). `suspect` readings never change status.
- Ops reaction to `point.status_changed`: `Watch` → open Watch alert; `Alert` → escalate/open Alert alert + create work order (priority High, Critical if depth ≥ 1.5 × alert threshold); `NoData` → DataGap alert + Medium "inspect device" work order; `Normal` → close open alerts for the point (work orders stay for humans). Idempotent by `eventId` (`processed_event` table).
- SLA: Critical 30 min, High 2 h, Medium 8 h, Low 24 h. Folio format `OT-YYYY-NNNNN`; citizen report `RC-YYYY-NNNNN`.

## Deviations

- T1 infrastructure logging: stock Mosquitto, Redis and PostgreSQL stdout logs use their native formats; Caddy access logs are JSON with its native field names/timestamp encoding. T5 must normalize these to §9 fields/ISO UTC in Promtail. Application services retain the exact §9 JSON contract. No custom broker plugins or new dependencies are introduced.

- T5 observability normalization: Mosquitto events use `mqtt.auth_success`, `mqtt.auth_failed`, `mqtt.acl_denied`; Caddy uses `http.access`. Promtail emits sanitized §9-style JSON/ISO UTC, discarding raw headers/query strings. Stock broker auth failures and ACL denials may lack username/IP; unknown IP is `unknown`, and SR-02 then alerts broker-wide without safe per-IP attribution. SR-06 account grouping and SR-07 account-age detection require producer fields absent from current logs; existing IP/out-of-hours branches remain active. See docs/siem-rules.md for exact limitations.

# Mérida Flood Monitoring & Early Warning — Alpha Prototype

SIS4415 · Segundo Parcial (Data-Driven 4.0, Units 3–4). Simulated IoT sensors → MQTT (TLS, IDMZ) → two microservices (FastAPI + ASP.NET Core) → PostgreSQL/TimescaleDB + Redis → real-time API/SignalR, with a SIEM-lite (Grafana/Loki) and CI.

**Status:** backend complete and running locally with Docker Compose. Frontend (Angular) is the next phase; cloud deploy is deferred.

## Docs map

| Doc | For |
|---|---|
| [CLAUDE.md](CLAUDE.md) / AGENTS.md | Agent instructions: personas per area, contracts, commands, workflow |
| [project.md](project.md) | Professor's requirements + rubric (English) |
| [architecture.md](architecture.md) | Design, all diagrams (Mermaid), rubric traceability — source for the Spanish PDF |
| [docs/contracts.md](docs/contracts.md) | Binding cross-service conventions (secrets, networks, events, auth, logs) |
| [docs/frontend-handoff.md](docs/frontend-handoff.md) | API + SignalR + auth guide for the Angular phase |
| [docs/frontend-kickoff-prompt.md](docs/frontend-kickoff-prompt.md) | Ready-to-paste prompt to start the frontend session |
| [docs/siem-rules.md](docs/siem-rules.md) | SIEM rules SR-01..07 and how to trigger them |
| [docs/plan.md](docs/plan.md) | Build plan and status |
| `services/*/README.md`, `simulator/README.md`, `infra/README.md`, `.github/README.md` | Per-component details |

## Quick start

Requirements: Docker (Compose v2), bash, openssl, python3.

```sh
bash scripts/bootstrap.sh        # generate ./secrets (git-ignored): passwords, TLS CA/certs, JWT keys
docker compose up -d --build     # ~11 containers, all healthchecked
python3 scripts/smoke.py         # end-to-end check through the gateway
```

- Gateway: https://localhost:8443 (`/api/telemetry/*`, `/api/ops/*`, `/hubs/live`, `/soc/` Grafana).
- Logins: `admin|supervisor|operator@flood.local`, passwords in `secrets/seed_*_password`; Grafana `admin` / `secrets/grafana_admin_password`.
- Demo storm: `SCENARIO=storm INTERVAL_SECONDS=10 docker compose up -d simulator`.
- SIEM demo (lab only): `docker compose --profile demo run --rm attack-sim` → alerts in Grafana → Alerting.
- Reset everything: `docker compose down -v`.

## Layout

```text
services/telemetry-service/   FastAPI: MQTT ingestion, validation, Timescale, status machine, KPIs, Open-Meteo
services/ops-service/         ASP.NET Core: auth (JWT RS256 cookies, MFA), ERP/MES work orders, SignalR
simulator/                    Python sensor simulator + attack simulator
infra/                        postgres, mosquitto, redis, caddy, observability (loki/promtail/grafana)
scripts/                      bootstrap.sh (secrets), smoke.py (e2e)
.github/                      CI (tests, CodeQL, gitleaks, Trivy, compose smoke)
```

## Tests

```sh
cd services/telemetry-service && uv run pytest     # + ruff, mypy
cd services/ops-service && dotnet test             # .NET 10 SDK
cd simulator && uv run pytest
python3 -m unittest discover -s infra/observability/tests
```

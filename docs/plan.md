# Backend Build Plan

Scope of this phase: **backend only** (services, simulator, infra, SIEM, CI). Frontend is a later phase — see [frontend-handoff.md](frontend-handoff.md).

## Tooling notes (for agents)

- .NET 10 SDK at `~/.dotnet`: `export DOTNET_ROOT=$HOME/.dotnet PATH=$HOME/.dotnet:$HOME/.dotnet/tools:$PATH DOTNET_NOLOGO=1 DOTNET_CLI_TELEMETRY_OPTOUT=1`. `dotnet-ef` 10.0.15 installed. NuGet packages already restored (offline builds work).
- Python: each project has a ready `.venv` (uv, Python 3.13). Run tools via `.venv/bin/pytest`, `.venv/bin/ruff`, `.venv/bin/mypy`.
- Agent sandboxes may have no network or Docker: do not add new packages; Docker/compose runs are done by the orchestrator.

## Tasks

| # | Task | Owner | Status |
|---|---|---|---|
| T0 | Docs, contracts, scaffolds, deps restored | Claude | done |
| T1 | Infra: bootstrap secrets, postgres init, mosquitto, redis, caddy, compose | Codex | done |
| T2 | Telemetry Service (FastAPI) + tests + Dockerfile | Codex | done |
| T3 | Operations Service (ASP.NET Core) + tests + Dockerfile | Codex | done |
| T4 | Simulator + attack-sim + Dockerfile | Codex | done |
| T5 | Observability/SIEM: Loki, Promtail, Grafana, alert rules SR-01..07 | Codex | done |
| T6 | GitHub Actions CI | Codex | done |
| T7 | Compose integration + end-to-end smoke | Claude | done |
| T8 | README, frontend handoff, commit + push to `pacheco` | Claude | done |
| F1/F2 | Integration bug fixes (readings 500, rain KPI, logging, SIEM SR-01/02) | Codex | done |

## Verified (local Docker, clean `down -v` → `up`)

- All 10 containers healthy; `scripts/smoke.py --lifecycle` passes (health, auth, CSRF, cross-service JWT, KPIs, readings, citizen report, SignalR, work order Open→Closed).
- Storm scenario: points Normal→Watch→Alert → ops alerts + work orders (OT-YYYY-NNNNN, SLA) automatically.
- SignalR pushes `pointStatus` live; attack-sim fires SR-01..SR-04 in Grafana (SR-05 verified earlier via jump readings; SR-06/07 have no attack-sim trigger yet).
- Tests: telemetry 84, ops 101, simulator 92, observability 17, scripts 13, CI helper 7 — all green.

## Next

1. Frontend (Angular) — [frontend-handoff.md](frontend-handoff.md).
2. Cloud VM deploy + CD workflow (`.github/README.md` has the design).
3. Spanish PDF report (teammate) from architecture.md + docs/.

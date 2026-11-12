# Backend Build Plan

Backend phase (T0–T8, F1/F2) and frontend phase (FE1–FE4) are done. Frontend guide: [frontend-handoff.md](frontend-handoff.md).

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
| FE0 | Design direction (impeccable decision round → "Semáforo de Protección Civil"), PRODUCT.md, surface brief | Claude | done |
| FE1 | Angular core: auth/CSRF/refresh interceptors, SignalR live service, signal stores, citizen view, login, ops shell + panel | Codex | done |
| FE2 | Point detail chart + thresholds, alerts, work-order board, reports, crews, map, users, audit, MFA; telemetry `/public/points` thresholds field | Codex | done |
| FE3 | Finish-review fixes (viewport-locked panel, order vs status semantics, sorting, 375 px, cross-tab refresh lock, tokens) | Codex + Claude | done |
| FE4 | Caddy multi-stage SPA build, CSP style nonce (templates), CI `frontend` job, Dependabot npm | Claude | done |

## Verified (local Docker, clean `down -v` → `up`)

- All 10 containers healthy; `scripts/smoke.py --lifecycle` passes (health, auth, CSRF, cross-service JWT, KPIs, readings, citizen report, SignalR, work order Open→Closed).
- Storm scenario: points Normal→Watch→Alert → ops alerts + work orders (OT-YYYY-NNNNN, SLA) automatically.
- SignalR pushes `pointStatus` live; attack-sim fires SR-01..SR-04 in Grafana (SR-05 verified earlier via jump readings; SR-06/07 have no attack-sim trigger yet).
- Tests: telemetry 84, ops 101, simulator 92, observability 17, scripts 13, CI helper 7, frontend 83 (Vitest) — all green.
- Frontend (browser, `ng serve` + gateway image): login, panel/band/ladder/KPIs/map update live during `SCENARIO=cycle` without reload, crew assignment on the work-order board, point chart with thresholds; no horizontal scroll at 375 px on all ops views; CSP nonce served by Caddy.
- Known limits: crews list needs Supervisor (Operators see crew id); MFA enable revokes refresh sessions (re-login later); alert-level filter is per page (API has no level filter); `storm` saturates the 150 cm sensor range → suspect readings → Sin datos (use `cycle` for demos).

## Next

1. Cloud VM deploy + CD workflow (`.github/README.md` has the design).
2. Spanish PDF report (teammate) from architecture.md + docs/.

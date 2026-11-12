# HTTPS gateway

Derived from pinned Caddy Alpine image; creates persistent data/config volumes
owned by UID 1000. Run via `docker compose up --build -d caddy` after services.
`SITE_ADDRESS=localhost`, `GATEWAY_HTTPS_PORT=8443`; only Caddy publishes ports.
`tls internal` uses a persistent local CA, independent of MQTT secrets.

Routes: `/api/telemetry/*` and `/api/ops/*` strip prefix; `/hubs/*` and `/soc/*`
retain prefix. WebSocket upgrades automatic. `/` serves the Angular SPA, built from `frontend/`
in the Dockerfile's first stage (build context = repo root); `templates` fills a
per-request CSP style nonce (`{http.request.uuid}`) into `index.html`.
One-MB request limit, security headers, JSON access logs on stdout. No events.

Static checks: telemetry venv Python `-m unittest discover -s scripts/tests -p test_compose.py -v`.
Orchestrator: run `docker compose run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile`;
verify HTTPS, redirect, headers, body limit and WebSocket routing live.
Grafana route requires T5; see `../README.md` for trust setup and log normalization.

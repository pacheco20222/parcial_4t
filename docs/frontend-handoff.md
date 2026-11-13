# Frontend Handoff (Angular)

Everything the frontend agent needs. Backend is done and running; build the SPA against it. Design context: [architecture.md](../architecture.md) §8 (views, KPIs), contracts: [contracts.md](contracts.md).

## Run the backend

```sh
bash scripts/bootstrap.sh          # once: generates ./secrets
docker compose up -d --build       # whole stack
python3 scripts/smoke.py           # sanity check
```

- Gateway: `https://localhost:8443` (Caddy local CA → accept the cert in the browser once).
- Demo logins: `admin@flood.local`, `supervisor@flood.local`, `operator@flood.local`; passwords in `secrets/seed_*_password`.
- Fast demo data: `SCENARIO=storm INTERVAL_SECONDS=10 docker compose up -d simulator` (points reach Watch → Alert in a few minutes; `cycle` = full Normal→Alert→Normal loop).

## Where the SPA lives

- App in `frontend/` (Angular 22, see `frontend/README.md`). `infra/caddy/Dockerfile` builds it in a Node stage (compose build context = repo root, `infra/caddy/Dockerfile.dockerignore`) and copies `dist/alerta-pluvial/browser` to `/srv/www`; SPA fallback `try_files {path} /index.html` uses `Cache-Control: no-cache`. Static asset paths bypass the fallback (missing chunks return 404); existing hashed assets use one-year immutable caching. Router import failures trigger at most one target-URL reload per tab session; blocked sessionStorage disables recovery to avoid loops.
- Same origin as the APIs → **no CORS**, cookies just work. Dev server: `ng serve` with `frontend/proxy.conf.json` (`/api`, `/hubs`, `/soc` → `https://localhost:8443`); the `/hubs` entry rewrites `Origin` because ops-service rejects cross-origin hub requests.
- CSP is strict (`default-src 'self'`, `connect-src 'self'`, images from OSM tiles). No inline scripts, no external CDNs (bundle fonts/libs). Leaflet tiles: `https://{s}.tile.openstreetmap.org`.
- Angular component styles need a nonce: Caddy's `templates` fills `ngCspNonce="{{placeholder `http.request.uuid`}}"` in `index.html` and the same value in `style-src 'self' 'nonce-…'`. Keep the backticks (Angular HTML-escapes double quotes when copying the nonce). No `style="…"` attributes in HTML strings (e.g. Leaflet `divIcon`); CSSOM (`el.style.x`) is fine. `inlineCritical` is off (its `onload` handler is blocked).

## Auth rules (must follow)

1. `POST /api/ops/auth/login` `{email, password}` → `200 {mfaRequired:false}` + HttpOnly cookies (`flood_at` 15 min JWT, `flood_rt` refresh). If `{mfaRequired:true}` → ask TOTP → `POST /api/ops/auth/mfa/verify {code}`.
2. **Every POST/PUT/PATCH/DELETE must send `X-Requested-With: XMLHttpRequest`** (CSRF) → use an Angular HTTP interceptor. Missing header = 403.
3. Tokens are never readable from JS. Session check: `GET /api/ops/auth/me` → `{id, email, roles[], mfaEnabled}` (401 = logged out).
4. On 401 → `POST /api/ops/auth/refresh` once, retry; if it fails → login page. Refresh proactively ~every 12 min while active.
5. `POST /api/ops/auth/logout`. Roles: `Operator` < `Supervisor` < `Admin`.
6. MFA enrollment: `POST /auth/mfa/setup` → `{otpauthUri}` (render QR client-side) → `POST /auth/mfa/enable {code}`.

## Endpoints (prefix shown is the gateway path)

### Telemetry — `/api/telemetry`

| Method | Path | Role | Response |
|---|---|---|---|
| GET | `/public/points` | public | `[{id, name, zone, lat, lon, status, simulated, watchThresholdCm, alertThresholdCm, waterDepthCm, updatedAt, lastUpdateAgeSeconds}]` — thresholds are floats read from DB on each request |
| GET | `/points/{id}/readings?from&to&bucket` | Operator | `[{capturedAt, waterDepthCm, rainMm5min}]` — bucket `1m|5m|15m|1h`, ISO UTC from/to, default last 6 h, max 7 d |
| GET | `/kpis` | Operator | `{pointsByStatus:{Normal,Watch,Alert,NoData}, maxDepthCm, rainLast60minMm, rainLast60minByPoint, dataFreshnessSeconds}` |
| GET | `/points/{id}/forecast` | Operator | `[{forecastFor, issuedAt, precipMm}]` (real Open-Meteo, hourly next 24 h) |
| PATCH | `/points/{id}/thresholds` | Supervisor | body `{watchThresholdCm, alertThresholdCm}` (0 < watch < alert ≤ 150) |

`status` ∈ `Normal | Watch | Alert | NoData`. `NoData` = stale sensor: show "sin datos", never 0.

### Operations — `/api/ops`

| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/public/reports` | public | `{pointId?, category, description≤500}` → `{id, folio, status}`; category `Encharcamiento|CalleIntransitable|DrenajeTapado|Otro`; rate-limited (5/10 min/IP); no personal data |
| GET | `/alerts?status&level&pointId&limit&offset` (`level` optional, `Watch\|Alert\|DataGap`, invalid → 400) | Operator | `[{id, pointId, pointName, zone, level(Watch|Alert|DataGap), status(Open|Closed), openedAt, closedAt, reason, depthCm}]` |
| PATCH | `/alerts/{id}` | Operator | `{status}` |
| GET | `/work-orders?status&priority&pointId&crewId&overdue&limit&offset` | Operator | `[{id, folio, alertId, citizenReportId, pointId, title, status, priority, crewId, createdAt, slaDueAt, assignedAt, onSiteAt, resolvedAt, closedAt, cancelReason, version}]` |
| POST | `/work-orders` | Supervisor | `{pointId, title, priority}` |
| PATCH | `/work-orders/{id}/assign` | Supervisor | `{crewId, version}` |
| PATCH | `/work-orders/{id}/transition` | Operator (Closed/Cancelled: Supervisor) | `{status, version, reason?}` (reason required for Cancelled) |
| GET | `/reports?status&pointId` · PATCH `/reports/{id}/validate` · `/reject` · `/link {workOrderId}` | Operator | citizen report moderation |
| GET / POST | `/crews` | Operator / Supervisor | `[{id, name, zone, available}]` · `{name, zone}` |
| GET | `/kpis` | Operator | `{openOrders, overdue, byPriority:[{priority,count}], avgMinutesAlertToOnSiteLast7Days, openAlertsByLevel:[{level,count}]}` |
| GET / POST | `/users` | Admin | `{email, password(≥12), role}` |
| GET | `/audit?limit&offset` | Admin | `[{id, userId, action, entity, at, ip}]` |

- **Optimistic concurrency:** send the work order's current `version`; `409` = changed by someone else → reload.
- Work order flow: `Open → Assigned → InProgress → Resolved → Closed`, or `Open → Cancelled`. Lists are plain arrays (max 100 per page; use `limit/offset`).
- Errors: ProblemDetails or `{error}`; show a generic message.

## Real-time — SignalR `/hubs/live`

```ts
new HubConnectionBuilder().withUrl('/hubs/live').withAutomaticReconnect().build();
```

Cookie auth is automatic (same origin). Anonymous connections get only `public` events.

| Client method | Group | Payload |
|---|---|---|
| `pointStatus` | public | `{pointId, status, waterDepthCm, capturedAt}` (every reading) |
| `reading` | ops | `{type, pointId, deviceId, capturedAt, waterDepthCm, rainMm5min, qualityFlag, status}` |
| `alert` | ops | alert object (as in `/alerts`) |
| `workOrder` | ops | work order object |
| `report` | ops | citizen report object |

On reconnect, re-fetch lists (events can be missed while offline).

## Views to build (architecture §8, rubric criterion 2)

- **Citizen (public, mobile-first):** map + list of points with status color and data age, citizen report form (shows folio), disclaimer "datos simulados".
- **Operator (mobile + desktop):** KPI cards (both `/kpis`), live map, per-point chart (readings + forecast + thresholds), alerts feed, work order board with actions, report moderation.
- **Supervisor/Admin:** assign crews, thresholds editor, users, audit log, link to SOC console `/soc/` (Grafana).
- Must be responsive and update live **without reload** (rubric "Excelente").

## Definition of done (frontend phase)

- `frontend/` Angular app (latest stable Angular, standalone, strict TS); `npm ci` lockfile committed; versions pinned.
- Production build served by Caddy (multi-stage `infra/caddy/Dockerfile` or mounted dist) with SPA fallback; CSP still strict.
- CI: add a `frontend` job (lint, unit tests, prod build) to `.github/workflows/ci.yml` and include it in `compose-smoke`; add `npm` ecosystem for `/frontend` to `.github/dependabot.yml` (ignore majors like the others).
- Works at 375 px and desktop; live updates without reload; Spanish UI copy; "datos simulados" disclaimer.
- Update this file, README and docs/plan.md.

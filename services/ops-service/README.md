# Operations service

.NET 10 municipal operations API: Identity/JWT/MFA, citizen reports (no personal-data fields), alerts, work orders, crews, audit, and SignalR. Owns PostgreSQL schema `ops`; never reads telemetry tables. Public report submission, live public point status, and health probes are intentional anonymous surfaces.

## Run and test

From this directory, with already restored packages:

```sh
export DOTNET_ROOT=$HOME/.dotnet PATH=$HOME/.dotnet:$HOME/.dotnet/tools:$PATH
export DOTNET_NOLOGO=1 DOTNET_CLI_TELEMETRY_OPTOUT=1
# -m:1 avoids MSBuild worker pipes in restricted sandboxes.
dotnet build --disable-build-servers --no-restore -m:1 -p:UseSharedCompilation=false
dotnet test --disable-build-servers --no-restore -m:1 -p:UseSharedCompilation=false
dotnet run --project src/Ops.Api --no-launch-profile --no-build
```

Sandbox verification compiles API and xUnit tests only; VSTest execution belongs to the orchestrator. Production integration requires PostgreSQL and Redis. Startup runs EF migrations then seeds roles/users. Initial migration is checked into source under `src/Ops.Api/Data/Migrations`; generate later migrations using `dotnet ef migrations add <Name> --project src/Ops.Api --output-dir Data/Migrations`.

## Configuration

Compose supplies environment variables; **all secret values come from files under `/run/secrets/`**:

| Variables | Default / meaning |
|---|---|
| `Database__Host`, `Database__Port`, `Database__Name`, `Database__User` | `postgres`, `5432`, `flood`, `ops_svc` |
| `Database__PasswordFile` | Required; `/run/secrets/ops_db_password` |
| `Redis__Host`, `Redis__Port`, `Redis__PasswordFile` | `redis`, `6379`, required `/run/secrets/redis_password` |
| `Jwt__PrivateKeyFile`, `Jwt__PublicKeyFile` | Required; `/run/secrets/jwt_private.pem`, `/run/secrets/jwt_public.pem`; matching RSA >= 2048 bits |
| `Seed__AdminPasswordFile`, `Seed__SupervisorPasswordFile`, `Seed__OperatorPasswordFile` | Optional `/run/secrets/seed_<role>_password`; skip user if absent |
| `Gateway__Ip` | Trusted gateway proxy IP; default `172.30.30.10` |
| `Security__EnforceMfa` | `false`; when true, Supervisor/Admin require `amr=mfa`, including inherited Operator access |
| `Operations__DefaultAlertThresholdCm` | `30` cm fallback when event and per-point setting omit alert threshold |
| `Operations__AlertThresholds__P01` (and each point ID) | Optional per-point alert threshold override |

Seed emails: `admin@flood.local`, `supervisor@flood.local`, `operator@flood.local`. Passwords: minimum 12 characters, Identity complexity requirements; lockout after 5 failures for 15 minutes. Seed files must satisfy policy; existing accounts are not overwritten. Access cookies last 15 minutes; rotating refresh families last 7 days per token. Logout revokes refresh family and clears cookies; already issued access JWTs expire naturally. MFA pending JWTs have a separate audience and 5-minute lifetime. TOTP key remains in private Identity storage; no filesystem-based data-protection keys are required by exposed auth flows.

**Priority:** status events carry `watchThresholdCm` and `alertThresholdCm`. Critical priority uses event depth >= 1.5 × event alert threshold. Legacy events without it use the per-point configured threshold, then the configured default. Invalid supplied thresholds are rejected before writes.

## HTTP contract

Listens on 8080. Routes have **no `/api/ops` prefix**; gateway strips it. Only forwarded headers from `Gateway__Ip` (default `172.30.30.10`) are trusted. Hub requests with an Origin must match the request scheme, host and effective port; absent Origin remains allowed. Every unsafe request, including login and SignalR negotiation, needs `X-Requested-With: XMLHttpRequest`. Cookies are Secure/HttpOnly/SameSite=Strict; access path `/`, refresh/pending paths `/api/ops/auth` (test raw service via HTTPS with explicit cookie headers). JSON is camelCase, enums are strings. Lists accept `limit` (1–100; default 50) and `offset` (0–100000).

| Routes | Behavior / role |
|---|---|
| `POST /auth/login` | `{email,password}`; 10 attempts / IP / 5 min; returns `{mfaRequired}` and cookies |
| `POST /auth/refresh`, `/auth/logout`; `GET /auth/me` | Rotation/reuse-family revocation, logout, authenticated profile |
| `POST /auth/mfa/setup`, `/auth/mfa/enable` | Authenticated; setup returns `otpauthUri`, enable accepts `{code}` |
| `POST /auth/mfa/verify` | Pending cookie + `{code}` completes login; 5 attempts / user / 15 min, keyed by validated pending-token `sub`; password login does not reset it |
| `POST /public/reports` | `{pointId?,category,description}`; max 500 characters; 5 / IP / 10 min; returns ID/folio/status only |
| `GET /alerts`, `/alerts/{id}`; `PATCH /alerts/{id}` | Operator+; filters `status`, `pointId`; PATCH `{status:"Closed"}` |
| `GET /work-orders`, `/work-orders/{id}` | Operator+; filters `status`, `priority`, `pointId`, `crewId`, `overdue` |
| `POST /work-orders` | Supervisor+; `{pointId,title,priority}` |
| `PATCH /work-orders/{id}/assign` | Supervisor+; `{crewId,version}` |
| `PATCH /work-orders/{id}/transition` | `{status,version,reason?}`; Operator+ InProgress/Resolved, Supervisor+ Closed/Cancelled |
| `GET /reports`, `/reports/{id}` | Operator+; filters `status`, `pointId` |
| `PATCH /reports/{id}/validate`, `/reject`, `/link` | Operator+; validate/reject pending reports; link validated report using `{workOrderId}` to existing order at same point |
| `GET /crews`; `POST /crews` | Supervisor+; create `{name,zone}`; 3 seeded zones |
| `GET /kpis` | Operator+; active/overdue counts, by priority, last-7-day alert→on-site mean (null if unavailable), open alerts by level |
| `GET /users`; `POST /users` | Admin; `{email,password,role}`; roles allowlist Operator/Supervisor/Admin |
| `GET /audit` | Admin; bounded audit history |
| `GET /healthz`, `/readyz` | Liveness; readiness checks DB + Redis, generic 503 on failure |
| `/hubs/live` | SignalR: everyone joins `public`, authorized Operator+ joins `ops`; expired auth connections close |

Lifecycle: Open → Assigned → InProgress → Resolved → Closed; only Open → Cancelled, with reason. Assignment sets crew; changes require current `version`, stale writes return 409. SLA: Critical 30m, High 2h, Medium 8h, Low 24h. Resolved/Closed/Cancelled are never overdue. Folios use PostgreSQL sequences (`OT-YYYY-NNNNN`, `RC-YYYY-NNNNN`), unique for service lifetime, with allowed sequence gaps.

Citizen validation does not dispatch crews: validate, create an order as Supervisor if needed, then link it. Users must not enter personal data in report free text.

## Events and deployment

Consumes `stream:point-status`, group `ops`, field `data`, starting at history; polls batches of 100, periodically XAUTOCLAIMs pending entries idle >=60s. Event validation failures remain pending for investigation. Per-point PostgreSQL advisory lock, `processed_event`, mutations and durable outbox commit together; XACK follows commit. Watch opens alert; Alert escalates/opens and creates High/Critical order; NoData creates DataGap + Medium inspection order; Normal closes alerts, leaves work orders. Duplicate event IDs have no effects.

Idle outbox polling backs off from 2 to 30 seconds; work resets polling to 1 second. Delivery can wait up to 30 seconds after idle. Failures also back off, capped at 30 seconds. Outbox publishes contract `{type,data}` envelopes to `events:ops` after commit, retrying on Redis failure. Delivery may duplicate after crash; clients should upsert by entity ID. Outbox is an additional ops-owned table. Pub/Sub subscriptions to `events:telemetry` and `events:ops` forward `reading`, `alert`, `workOrder`, `report` to `ops`; public `pointStatus` contains only `pointId,status,waterDepthCm,capturedAt`. Committed stream transitions also push public status immediately (including NoData, with event occurrence time).

JSON console logs expose top-level `ts,level,service,event`, structured `client_ip,user,path,point_id` where applicable. All entries include rendered `msg`; exceptions include `exc` type, message and traceback (including inner exceptions). EF sensitive data logging stays disabled, Npgsql error detail stays disabled, and EF database command logging is Warning. No request bodies, tokens, cookies or passwords are explicitly logged. Privileged mutations write audit rows and `audit.*` events. Built-in rate limits are per process (MFA per user, other limits per IP); use one Alpha replica or enforce shared limits at gateway when scaling.

Npgsql disables GSS encryption negotiation (`Gss Encryption Mode=Disable`) for password-authenticated PostgreSQL, avoiding the missing Kerberos library startup probe. No additional packages required.

Docker build context: this directory. Dockerfile pins SDK `10.0.404` / runtime `10.0.15`, runs as image APP_UID, exposes 8080; CLI `--healthcheck` needs no curl or secrets. Run read-only with writable `/tmp` tmpfs, mounted readable secret files, schema-owner `ops_svc` (DDL for startup migration), and Redis access. Orchestrator must build image, run migrations against actual PostgreSQL, verify Redis redelivery/reconnect/backplane, gateway HTTPS cookies, healthcheck, and read-only-root execution. EF InMemory tests do not prove PostgreSQL constraints, locks, sequence allocation or actual Redis delivery.

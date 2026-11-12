# Flood SOC

Single-node Loki (filesystem, seven-day retention), Docker-discovered Promtail logs,
and Grafana **SOC — Flood Platform** dashboard plus SR-01–SR-07 alerts.

## Run and test

From repository root, after orchestrator runs bootstrap:

```sh
docker compose up -d loki promtail grafana
python3 -m unittest discover -s infra/observability/tests -v
docker compose config -q
```

Tests use existing host Python/PyYAML; no dependencies are added. They check YAML,
Compose hardening, real broker-format regex fixtures, provisioning references,
rule thresholds, UTC/Mérida time boundaries, and documentation/query consistency.
They do not execute Promtail templates, LogQL, or Grafana provisioning.

Open `https://localhost:8443/soc/` through Caddy; log in as `admin` with generated
`secrets/grafana_admin_password`. No observability ports are published. Caddy's
existing `/soc/*` route preserves the prefix. Use trailing slash. Other hostnames,
ports or deployments need the public HTTPS Grafana root URL reviewed during integration.

Grafana reads `GF_SECURITY_ADMIN_PASSWORD__FILE=/run/secrets/grafana_admin_password`.
Compose sets subpath serving, Secure/Strict cookies, anonymous/sign-up disabled,
JSON console logs and update/analytics checks disabled. No other secrets required.
The generated password bootstraps a new Grafana database; changing the secret alone
does not rotate an existing Grafana administrator password.

## Collection and storage

`promtail.yaml` discovers only Compose project `merida-flood`; overriding Compose
project name requires updating its Docker label filter. Services are selected by
`com.docker.compose.service`. Loki stream labels: job, service, event, level.
IPs, accounts and devices stay inside JSON to bound cardinality. Flat service JSON,
legacy ASP.NET `State`/first `Scopes` entry, broker native text and Caddy JSON are
normalized. Caddy query strings, raw headers, cookies, framework messages and arbitrary
fields are discarded. Caddy timestamps become ISO UTC; native unstructured logs
without timestamps use collection time. Unsupported PostgreSQL text becomes a
sanitized `service.log` record; there are no database-specific detection rules.

Broker events: `mqtt.auth_success`, `mqtt.auth_failed`, `mqtt.acl_denied`.
Failed-login client IDs are retained in JSON, never trusted as usernames. Native
Mosquitto failures lack source IP; SR-02 counts ≥5 broker-wide failures in 60 seconds.
SR-01 demo: run attack-sim `foreign_network` from its OT+IDMZ attachments; TCP uses
`172.30.20.10`, TLS verifies `mosquitto`. Reducers retain `replaceNN` with value `0`.
Application events keep contract §9 names. All alert queries and source limitations:
[SIEM rules](../../docs/siem-rules.md).

Named volumes `lokidata`, `grafanadata`, `promtailpositions` retain data/state.
Config/provisioning/dashboard bind mounts are read-only. Loki and Grafana run as
image non-root UIDs, with writable data volumes and `/tmp` only. Never run recursive
host chown or broad permission changes to work around a deployment failure.

**Docker socket risk:** Promtail runs as root to access a typical root-owned
socket. Mounting `docker.sock:ro` does **not** make Docker API operations read-only;
a compromised collector can control the host. This is an explicit Alpha tradeoff.
Use a restricted socket proxy in a hardened deployment. Alternative: remove socket
and Docker discovery, mount `/var/lib/docker/containers:ro`, configure static file
scrapes with `docker: {}` decoding and explicit service labels. That alternative
requires Docker `json-file` logs, Linux host paths, and manual labels (Docker Desktop
paths reside inside its VM). No proxy dependency is added here.

## Alerts and integration verification

Alerts evaluate every 30 seconds; absent events are OK, query execution errors are
visible Error states. No remediation is automatic. `soc-alerts` is the default
contact point with a loopback placeholder, muted all day by catch-all route.
An example external URL is commented only; no listener or external endpoint is used.
Alerts still appear in Grafana. To enable delivery intentionally, set a real approved
receiver and remove `soc-delivery-disabled` route/mute interval; enable resolved
messages if wanted. Never put credentials in a committed URL.

Orchestrator must validate pinned-image availability/security and actual startup:
Loki `-verify-config=true`, Promtail `-check-syntax`, Grafana provisioning logs,
queries against live fixtures, dashboard, all-day mute and `/soc/` login redirects.
Promtail readiness: `:9080/ready`; Loki readiness: `:3100/ready`; Grafana health:
`:3000/soc/api/health`. Access these only from `mon_net`.
Loki's distroless healthcheck checks binary liveness (`-version`), not HTTP readiness;
Compose ordering uses `service_started`. Grafana and Promtail healthchecks use
HTTP readiness. Docker/socket permissions, named-volume ownership, image healthcheck
tooling and full attack-sim detections require Docker integration proof.

Versions are pinned to available design-era tags, not claimed current or vulnerability-free.
Promtail is retained as explicitly requested; plan collector migration separately.

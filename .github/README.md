# Backend CI

Every push and pull request runs .NET 10 restore/format/build/tests, Python 3.13
frozen uv sync plus Ruff/pytest (and telemetry mypy), Gitleaks, and C#/Python
CodeQL with no-build analysis. Formatting is advisory during Alpha. Only CodeQL
receives `security-events: write`; checkout never persists credentials.

After service checks pass, Buildx loads three images locally with per-image GHA
caches. Trivy reports fixed HIGH/CRITICAL findings and fails on fixed CRITICAL
findings. Images are not published. Compose smoke runs on a separate runner and
rebuilds images, bootstraps ephemeral file-backed secrets, starts only Caddy,
simulator and their dependencies, checks health, waits at most 120 seconds for
five points with `updatedAt`, then runs `python3 scripts/smoke.py`. Failure logs
are printed; containers and volumes are always removed. Demo attacks and the SOC
stack are excluded. No CI secrets are required for the local smoke stack.

Local helper tests (stdlib only):

```sh
python3 -m unittest discover -s .github/ci -p 'test_*.py' -v
```

With Docker available, reproduce smoke from the repository root:

```sh
export COMPOSE_FILE=docker-compose.yml:.github/ci/compose.ci.yml
export OPEN_METEO_ENABLED=false SECURITY_ENFORCE_MFA=false GATEWAY_HTTPS_PORT=8443
bash scripts/bootstrap.sh
docker compose up -d --build --wait --wait-timeout 240 caddy simulator
python3 .github/ci/wait_for_readings.py
python3 scripts/smoke.py
docker compose down -v --remove-orphans
```

The override sets simulator `INTERVAL_SECONDS=10`. Bootstrap creates ignored
`secrets/` files; services consume explicit mounts under `/run/secrets`, never
secret values in environment variables. Readiness uses only the public points
endpoint; smoke also checks auth, CSRF, KPIs, reports and SignalR. CI defines no
new application endpoints or events.

Dependabot checks NuGet, both uv projects, every Dockerfile directory and Actions
weekly. All third-party actions are pinned to full commit SHAs (version in comment).
CodeQL is skipped while the repo is private (code scanning needs GitHub Advanced Security); fork PR tokens
may restrict SARIF upload. Organization-owned repositories may need a Gitleaks
license configured separately as `GITLEAKS_LICENSE` in the action environment.

## Continuous deployment

`cd.yml` exposes the manual **Deploy** button on `main` only. The `production`
environment requires owner approval; `deploy-production` concurrency serializes
deployments without cancelling the running job. It does not run CI automatically:
check Backend CI is green for the selected commit before approving.

The runner ships a full-history `main` Git bundle over SSH, so the private repo
needs no GitHub credentials on the VPS. The dedicated key can invoke only
`/opt/parcial_4t/scripts/ci-deploy.sh` as `claude4t`. That receiver caps input at
50 MiB, verifies the bundle, fast-forwards `main`, reads the existing `.env`
`SITE_ADDRESS`, and calls the existing deployment helper with `SKIP_PULL=1` and
`BEHIND_PROXY=1`. Application secrets remain file-backed; no new endpoints or
application events are introduced. Receiver JSON logs use `deploy.*` events;
client command text is never executed or printed (only its presence is logged).

Production environment secrets: `VPS_SSH_KEY`, `VPS_KNOWN_HOSTS`, `VPS_USER`
(`claude4t`), `VPS_HOST`, `GATE_USER`, and `GATE_PASSWORD`. Set `SITE_ADDRESS` as
an environment variable or secret (hostname only). SSH requires the pinned host
key; the runner never learns host keys on first connection. The temporary SSH
key is mode 0600 and shredded on exit and by an always-run cleanup step. Public
validation calls `https://<SITE_ADDRESS>/api/telemetry/healthz` through Basic Auth.

Setup and manual run: [VPS deployment](../docs/deploy-vps.md#continuous-deployment).
Offline checks from the repository root (existing telemetry environment):

```sh
bash -n scripts/ci-deploy.sh
services/telemetry-service/.venv/bin/python -c 'import yaml; yaml.safe_load(open(".github/workflows/cd.yml"))'
services/telemetry-service/.venv/bin/python -m unittest discover -s scripts/tests
```

These checks do not prove SSH access, required-reviewer enforcement, Docker
builds, or public health. A failed deploy exits nonzero; no automatic rollback
or volume deletion is performed. Use the existing operator deployment procedure
to recover, preserving volumes and secrets.

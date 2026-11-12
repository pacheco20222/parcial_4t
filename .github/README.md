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

CD is deferred: publish GHCR images tagged by immutable commit SHA, deploy over
SSH only after GitHub environment approval, and roll back by selecting the
previous SHA tag. No publish/deploy workflow or write permission is enabled here.

#!/usr/bin/env bash
# Deploy/update the stack on the presentation VPS (Ubuntu, run as the non-root deploy user).
# Usage: SITE_ADDRESS=<host or a-b-c-d.sslip.io> bash scripts/deploy-vps.sh
# Idempotent: safe to re-run for updates (git pull + rebuild). Never deletes volumes or secrets.
set -euo pipefail

: "${SITE_ADDRESS:?set SITE_ADDRESS (domain or <ip-with-dashes>.sslip.io)}"
cd "$(dirname "$0")/.."

command -v docker >/dev/null || { echo "Docker missing: see docs/deploy-vps.md step 2" >&2; exit 1; }

# Production settings (kept in a git-ignored .env next to docker-compose.yml)
cat > .env <<EOF
SITE_ADDRESS=${SITE_ADDRESS}
TLS_MODE=acme
GATEWAY_HTTPS_PORT=443
GATEWAY_HTTP_PORT=80
GATE_MODE=on
GATE_USER=${GATE_USER:-demo}
ENVIRONMENT=prod
SCENARIO=${SCENARIO:-cycle}
INTERVAL_SECONDS=${INTERVAL_SECONDS:-10}
EOF
chmod 600 .env

git pull --ff-only
bash scripts/bootstrap.sh                       # only creates missing secrets
docker compose up -d --build --wait --remove-orphans
python3 scripts/smoke.py --base "https://${SITE_ADDRESS}" --gate

echo
echo "Deployed: https://${SITE_ADDRESS}"
echo "Site gate user: ${GATE_USER:-demo}  password: secrets/gate_password"
echo "App logins: secrets/seed_*_password  | Grafana: /soc/ (admin, secrets/grafana_admin_password)"

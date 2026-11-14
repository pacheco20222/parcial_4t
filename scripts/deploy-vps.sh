#!/usr/bin/env bash
# Deploy/update the stack on the presentation VPS (run as the deploy user, from the repo checkout).
#   SITE_ADDRESS=<host or a-b-c-d.sslip.io> bash scripts/deploy-vps.sh
# Default BEHIND_PROXY=1: shared VPS whose host nginx owns 80/443 and proxies to our Caddy on
# 127.0.0.1:8443 (infra/nginx/parcial4t.conf). BEHIND_PROXY=0: dedicated VPS, Caddy binds 80/443
# itself and gets Let's Encrypt certificates.
# Idempotent: re-run to update (git pull + rebuild). Never deletes volumes or secrets.
set -euo pipefail

: "${SITE_ADDRESS:?set SITE_ADDRESS (domain or <ip-with-dashes>.sslip.io)}"
BEHIND_PROXY="${BEHIND_PROXY:-1}"
cd "$(dirname "$0")/.."

command -v docker >/dev/null || { echo "Docker missing: see docs/deploy-vps.md" >&2; exit 1; }

if [[ "$BEHIND_PROXY" == "1" ]]; then
  net=$'TLS_MODE=internal\nGATEWAY_BIND=127.0.0.1\nGATEWAY_HTTPS_PORT=8443\nGATEWAY_HTTP_PORT=8081\nTRUSTED_PROXIES=172.30.0.1/32'
else
  net=$'TLS_MODE=acme\nGATEWAY_BIND=0.0.0.0\nGATEWAY_HTTPS_PORT=443\nGATEWAY_HTTP_PORT=80'
fi

# Production settings (git-ignored .env next to docker-compose.yml)
cat > .env <<EOF
SITE_ADDRESS=${SITE_ADDRESS}
${net}
GATE_MODE=on
GATE_USER=${GATE_USER:-demo}
ENVIRONMENT=prod
COMPOSE_PROFILES=soc-demo
ATTACK_INTERVAL_MINUTES=${ATTACK_INTERVAL_MINUTES:-12}
SCENARIO=${SCENARIO:-cycle}
INTERVAL_SECONDS=${INTERVAL_SECONDS:-10}
EOF
chmod 600 .env

[[ "${SKIP_PULL:-0}" == "1" ]] || git pull --ff-only   # SKIP_PULL=1 when code arrives via git bundle (private repo)
bash scripts/bootstrap.sh                       # only creates missing secrets
# Low CPU/IO priority so image builds don't slow down other services on a shared host.
nice -n 10 ionice -c3 docker compose build
docker compose up -d --wait --remove-orphans
if [[ "$BEHIND_PROXY" == "1" ]]; then
  # Shared host: no hairpin to its own public IP. Smoke the stack from edge_net, verifying Caddy's local CA.
  cip=$(docker inspect merida-flood-caddy-1 --format '{{(index .NetworkSettings.Networks "merida-flood_edge_net").IPAddress}}')
  ca=$(mktemp); trap 'rm -f "$ca"' EXIT
  docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt "$ca" >/dev/null
  chmod 644 "$ca"
  docker run --rm --network merida-flood_edge_net --add-host "${SITE_ADDRESS}:${cip}" \
    -v "$PWD:/repo:ro" -v "$ca:/ca.crt:ro" -e GATE_MODE=on -w /repo python:3.13.18-slim-trixie \
    python scripts/smoke.py --base "https://${SITE_ADDRESS}" --ca /ca.crt
else
  python3 scripts/smoke.py --base "https://${SITE_ADDRESS}" --gate
fi

echo
echo "Deployed: https://${SITE_ADDRESS}"
echo "Site gate user: ${GATE_USER:-demo}  password: secrets/gate_password"
echo "App logins: secrets/seed_*_password  | Grafana: /soc/ (admin, secrets/grafana_admin_password)"

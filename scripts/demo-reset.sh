#!/usr/bin/env bash
# Reset demo activity only. Run against the local Compose project.
set -euo pipefail

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--yes" ) ]]; then
  echo "Usage: $0 [--yes]" >&2
  exit 2
fi
if [[ "${1:-}" != "--yes" ]]; then
  echo 'This deletes demo alerts, orders and citizen reports. Type RESET to continue:'
  IFS= read -r answer || exit 1
  if [[ "$answer" != "RESET" ]]; then
    echo 'Reset cancelled.' >&2
    exit 1
  fi
fi

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
docker compose exec -T postgres psql -U postgres -d flood -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
TRUNCATE ops.alert, ops.work_order, ops.citizen_report,
         ops.processed_event, ops.outbox_message RESTART IDENTITY CASCADE;
ALTER SEQUENCE ops.work_order_seq RESTART WITH 1;
ALTER SEQUENCE ops.citizen_report_seq RESTART WITH 1;
UPDATE telemetry.monitoring_point SET status = 'Normal';
COMMIT;
SQL

# Read the mounted secret inside Redis; never put the password in argv.
# SCAN explicitly checks each exit status before proceeding (no masking pipeline).
docker compose exec -T redis sh -eu <<'REDIS'
export REDISCLI_AUTH="$(cat /run/secrets/redis_password)"
cursor=0
while :; do
  page=$(redis-cli --raw SCAN "$cursor" MATCH 'cache:kpis:*' COUNT 100)
  cursor=$(printf '%s\n' "$page" | head -n 1)
  case "$cursor" in ''|*[!0-9]*) echo 'Redis SCAN failed' >&2; exit 1 ;; esac
  keys=$(printf '%s\n' "$page" | tail -n +2)
  if [ -n "$keys" ]; then
    # KPI key names contain no newlines. Quoting preserves each key verbatim.
    printf '%s\n' "$keys" | while IFS= read -r key; do
      case "$key" in cache:kpis:*) ;; *) echo 'Unexpected cache key' >&2; exit 1 ;; esac
      deleted=$(redis-cli --raw DEL "$key")
      case "$deleted" in 0|1) ;; *) echo 'Redis DEL failed' >&2; exit 1 ;; esac
    done
  fi
  [ "$cursor" != 0 ] || break
done
REDIS

docker compose restart simulator citizen-bot
echo 'Demo reset: alerts, orders and reports cleared; point status Normal; KPI caches cleared; simulators restarted.'
echo 'Users, crews, audit history, readings, stream backlog and secrets preserved.'

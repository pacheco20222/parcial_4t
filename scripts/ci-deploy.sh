#!/usr/bin/env bash
# SSH forced-command receiver. Run only as claude4t on the presentation VPS.
set -euo pipefail
umask 077

readonly ROOT=/opt/parcial_4t
readonly MAX_BYTES=52428800 # 50 MiB
bundle=''

log() {
  printf '{"ts":"%s","level":"%s","service":"ci-deploy","event":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >&2
}

cleanup() {
  local status=$?
  trap - EXIT
  if [[ -n "$bundle" ]]; then
    rm -f -- "$bundle"
  fi
  if (( status != 0 )); then
    log error deploy.failed
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cd "$ROOT"
if [[ -n "${SSH_ORIGINAL_COMMAND:-}" ]]; then
  # Record presence only: arbitrary client text could contain credentials.
  log info deploy.original_command_ignored
fi

# A bundle's main must update the server's main, never another checked-out branch.
[[ "$(git -C "$ROOT" symbolic-ref --short HEAD)" == main ]] || {
  log error deploy.main_required
  exit 1
}
bundle=$(mktemp "$ROOT/.ci-deploy.XXXXXXXX")
log info deploy.receiving_bundle
# Read one extra byte to reject oversized input without unbounded disk writes.
head -c "$((MAX_BYTES + 1))" > "$bundle"
size=$(wc -c < "$bundle")
if (( size == 0 || size > MAX_BYTES )); then
  log error deploy.invalid_bundle_size
  exit 1
fi
git -C "$ROOT" bundle verify "$bundle"
log info deploy.fast_forward
git -C "$ROOT" pull --ff-only "$bundle" main

# Read data, never execute .env contents. deploy-vps.sh writes bare host values.
SITE_ADDRESS=''
while IFS= read -r line || [[ -n "$line" ]]; do
  if [[ "$line" == SITE_ADDRESS=* ]]; then
    SITE_ADDRESS=${line#SITE_ADDRESS=}
  fi
done < "$ROOT/.env"
if [[ ! "$SITE_ADDRESS" =~ ^[[:alnum:]]([[:alnum:].-]*[[:alnum:]])?$ ]] \
  || (( ${#SITE_ADDRESS} > 253 )); then
  log error deploy.invalid_site_address
  exit 1
fi

log info deploy.starting
SKIP_PULL=1 BEHIND_PROXY=1 SITE_ADDRESS="$SITE_ADDRESS" bash scripts/deploy-vps.sh
log info deploy.completed

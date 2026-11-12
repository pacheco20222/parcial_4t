#!/usr/bin/env bash
set -euo pipefail
umask 077
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
force=false
case "${1:-}" in
  '') ;;
  --force) force=true ;;
  *) echo 'Usage: scripts/bootstrap.sh [--force]' >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { echo 'Too many arguments' >&2; exit 2; }
for tool in openssl python3 docker; do
  command -v "$tool" >/dev/null || { echo "Required tool missing: $tool" >&2; exit 1; }
done
secrets="$root/secrets"
[[ ! -L "$secrets" ]] || { echo 'Refusing symlink secrets directory' >&2; exit 1; }
mkdir -p "$secrets"
chmod 700 "$secrets"
if [[ -n "$(find "$secrets" -maxdepth 1 -type l -print -quit)" ]]; then
  echo 'Refusing symlink secret files' >&2; exit 1
fi
work="$(mktemp -d "$secrets/.bootstrap.XXXXXX")"
trap 'rm -rf -- "$work"' EXIT
needs() { [[ "$force" == true || ! -f "$secrets/$1" ]]; }
install_secret() {
  # Compose file-backed secrets preserve host modes. 0644 permits non-root
  # container UIDs to read explicit mounts; host traversal is blocked by 0700.
  chmod 644 "$work/$1"
  mv -f -- "$work/$1" "$secrets/$1"
}
mqtt_changed=false
for name in postgres_password telemetry_db_password ops_db_password redis_password \
  mqtt_telemetry_password seed_admin_password seed_supervisor_password \
  seed_operator_password grafana_admin_password; do
  if needs "$name"; then
    case "$name" in
      seed_*)
        # Keep 256 random bits and satisfy standard ASP.NET Identity classes.
        openssl rand -hex 32 | tr -d '\n' > "$work/$name"
        printf 'Aa1!\n' >> "$work/$name"
        ;;
      *) openssl rand -hex 32 > "$work/$name" ;;
    esac
    install_secret "$name"
    if [[ "$name" == mqtt_telemetry_password ]]; then mqtt_changed=true; fi
  fi
done
if needs mqtt_devices.json; then
  python3 - "$work/mqtt_devices.json" <<'PY'
import json, subprocess, sys
passwords = {f"DEV-P0{i}-A": subprocess.check_output(
    ["openssl", "rand", "-hex", "32"], text=True).strip() for i in range(1, 6)}
with open(sys.argv[1], "w") as out:
    json.dump(passwords, out)
    out.write("\n")
PY
  install_secret mqtt_devices.json
  mqtt_changed=true
fi
ca_changed=false
if needs ca.key; then
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$work/ca.key" 2>/dev/null
  install_secret ca.key
  ca_changed=true
fi
if needs ca.crt || [[ "$ca_changed" == true ]]; then
  cat > "$work/ca.cnf" <<'CNF'
[req]
distinguished_name = dn
x509_extensions = ca
prompt = no
[dn]
CN = Merida Flood Development CA
[ca]
basicConstraints = critical,CA:TRUE
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
CNF
  openssl req -new -x509 -sha256 -days 3650 -key "$secrets/ca.key" \
    -config "$work/ca.cnf" -out "$work/ca.crt"
  install_secret ca.crt
  ca_changed=true
fi
server_changed=false
if needs mqtt_server.key; then
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$work/mqtt_server.key" 2>/dev/null
  install_secret mqtt_server.key
  server_changed=true
fi
if needs mqtt_server.crt || [[ "$ca_changed" == true || "$server_changed" == true ]]; then
  openssl req -new -key "$secrets/mqtt_server.key" -subj '/CN=mosquitto' -out "$work/server.csr"
  cat > "$work/server.ext" <<'CNF'
subjectAltName=DNS:mosquitto,DNS:localhost
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
CNF
  openssl x509 -req -sha256 -days 825 -in "$work/server.csr" \
    -CA "$secrets/ca.crt" -CAkey "$secrets/ca.key" \
    -set_serial "0x$(openssl rand -hex 16)" -extfile "$work/server.ext" -out "$work/mqtt_server.crt"
  install_secret mqtt_server.crt
fi
jwt_changed=false
if needs jwt_private.pem; then
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$work/jwt_private.pem" 2>/dev/null
  install_secret jwt_private.pem
  jwt_changed=true
fi
if needs jwt_public.pem || [[ "$jwt_changed" == true ]]; then
  openssl pkey -in "$secrets/jwt_private.pem" -pubout -out "$work/jwt_public.pem"
  install_secret jwt_public.pem
fi
if needs mosquitto_passwd || [[ "$mqtt_changed" == true ]]; then
  python3 - "$secrets" "$work/mosquitto_passwd" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
users = json.loads((root / "mqtt_devices.json").read_text())
expected = {f"DEV-P0{i}-A" for i in range(1, 6)}
if set(users) != expected:
    raise SystemExit("mqtt_devices.json must contain exactly DEV-P01-A..DEV-P05-A")
users["svc-telemetry"] = (root / "mqtt_telemetry_password").read_text().strip()
if any(not isinstance(pw, str) or not pw or any(c in pw for c in ':\r\n') for pw in users.values()):
    raise SystemExit("Invalid MQTT password")
with open(sys.argv[2], "w") as out:
    out.writelines(f"{user}:{pw}\n" for user, pw in users.items())
PY
  # Docker is required. Passwords travel via a private file, never process argv.
  docker run --rm --network none --user "$(id -u):$(id -g)" \
    --cap-drop ALL --security-opt no-new-privileges --read-only --tmpfs /tmp \
    --mount "type=bind,src=$work,dst=/work" --entrypoint mosquitto_passwd \
    eclipse-mosquitto:2.0.22 -U /work/mosquitto_passwd
  install_secret mosquitto_passwd
fi
# Site gate for the public demo (used only when GATE_MODE=on). The hash is derived
# from gate_password; existing files are kept unless --force.
if needs gate_password; then
  openssl rand -hex 16 | tr -d '\n' > "$work/gate_password"
  install_secret gate_password
  rm -f -- "$secrets/gate_password_hash"
fi
if needs gate_password_hash; then
  # Password travels via stdin, never argv.
  docker run --rm -i caddy:2.10.2-alpine caddy hash-password --algorithm bcrypt \
    < <(cat "$secrets/gate_password"; echo) | tr -d '\n' > "$work/gate_password_hash"
  [[ -s "$work/gate_password_hash" ]] || { echo 'gate hash generation failed' >&2; exit 1; }
  install_secret gate_password_hash
fi
# Also repair modes on existing files without changing their contents.
find "$secrets" -maxdepth 1 -type f -exec chmod 644 {} +
printf 'Bootstrap complete. Secrets stored in %s\n' "$secrets"

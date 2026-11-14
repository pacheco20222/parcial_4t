# Deploy to the Hostinger VPS (presentation)

Temporary IaaS deployment: one Hostinger VPS running the same Docker Compose stack as local. Delete the VPS after the presentation.

**Plan:** KVM 2 (2 vCPU / 8 GB) recommended (KVM 1 / 4 GB is tight). **OS:** Ubuntu 24.04 LTS.
**Hostname:** your domain (A record → VPS IP) or free `sslip.io`: IP `203.0.113.7` → `203-0-113-7.sslip.io`. Caddy gets a Let's Encrypt certificate automatically (ports 80/443 must be open).


## Shared VPS (host nginx already owns 80/443) — default mode

Our stack binds only `127.0.0.1:8443`; the host nginx terminates public TLS and proxies to it. Nothing else on the host changes (existing sites, ports, firewall).

```sh
sudo mkdir -p /opt/parcial_4t && sudo chown $USER: /opt/parcial_4t
git clone https://github.com/pacheco20222/parcial_4t.git /opt/parcial_4t && cd /opt/parcial_4t
SITE_ADDRESS=2-25-112-211.sslip.io bash scripts/deploy-vps.sh            # BEHIND_PROXY=1 (default)
H=2-25-112-211.sslip.io
sed "s/__HOST__/$H/g" infra/nginx/parcial4t.conf | sudo tee /etc/nginx/sites-available/parcial4t
sudo ln -s /etc/nginx/sites-available/parcial4t /etc/nginx/sites-enabled/parcial4t
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d $H                                             # renewed by the existing certbot.timer
```

Teardown on a shared VPS: `docker compose down -v` in `/opt/parcial_4t`, remove `/etc/nginx/sites-{enabled,available}/parcial4t`, `sudo nginx -t && sudo systemctl reload nginx`, `sudo certbot delete --cert-name $H`, `sudo rm -rf /opt/parcial_4t`.

## Continuous deployment

Manual **Actions → Deploy → Run workflow → main** ships code from the runner,
including for a private repository. Approve the `production` environment only
after Backend CI passes for that commit. Deployment is serialized, never
automatically cancelled; only `main` is accepted. This workflow builds on the
VPS rather than publishing images.

Prerequisites: the existing checkout at `/opt/parcial_4t` belongs to `claude4t`,
is on `main`, and already contains executable `scripts/ci-deploy.sh` and the
`SKIP_PULL`-aware deployment helper. Install these initially through the existing
administrator access. Keep the working tree clean and `.env` present with a bare
`SITE_ADDRESS=hostname` line. The receiver never executes `.env` as shell code.
`claude4t` needs the existing Docker access; no sudo or new host-wide changes are
part of CD. Existing host nginx, firewall, and other projects stay under their
current administration. Docker access itself is privileged; the forced command
limits this key's SSH entry point, not Docker's host permissions.

One-time setup on a trusted operator machine (replace the VPS placeholder):

```sh
REPO=pacheco20222/parcial_4t
VPS_HOST='<VPS_IP_OR_HOSTNAME>'
ssh-keygen -t ed25519 -f parcial4t_cd -N ''

# Use an existing administrative SSH identity, never the new CD key, to install.
cat parcial4t_cd.pub | ssh "claude4t@$VPS_HOST" \
  'umask 077; mkdir -p "$HOME/.ssh"; chmod 700 "$HOME/.ssh";
   { printf '\''command="/opt/parcial_4t/scripts/ci-deploy.sh",restrict '\''; cat; } >> "$HOME/.ssh/authorized_keys";
   chmod 600 "$HOME/.ssh/authorized_keys"'

ssh-keyscan -t ed25519 "$VPS_HOST" > parcial4t_known_hosts
ssh-keygen -lf parcial4t_known_hosts
```

Before storing `parcial4t_known_hosts`, compare that fingerprint with the host's
`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` through the trusted VPS console.
`ssh-keyscan` alone does not authenticate the server. The runner uses
`StrictHostKeyChecking=yes` with this verified file, never TOFU.

Create the protected environment and install secrets (authenticated `gh` with
repository administration rights; example assumes a user-owned repository):

```sh
OWNER=$(gh api "repos/$REPO" --jq '.owner.login')
OWNER_ID=$(gh api "users/$OWNER" --jq '.id')
gh api --method PUT "repos/$REPO/environments/production" --input - <<EOF
{
  "wait_timer": 0,
  "prevent_self_review": false,
  "reviewers": [{"type": "User", "id": $OWNER_ID}],
  "deployment_branch_policy": null
}
EOF
gh api "repos/$REPO/environments/production" --jq '.protection_rules'

gh secret set --repo "$REPO" --env production VPS_SSH_KEY < parcial4t_cd
gh secret set --repo "$REPO" --env production VPS_KNOWN_HOSTS < parcial4t_known_hosts
printf '%s' claude4t | gh secret set --repo "$REPO" --env production VPS_USER
printf '%s' "$VPS_HOST" | gh secret set --repo "$REPO" --env production VPS_HOST
gh secret set --repo "$REPO" --env production GATE_USER
gh secret set --repo "$REPO" --env production GATE_PASSWORD
gh variable set --repo "$REPO" --env production SITE_ADDRESS --body '<PUBLIC_HOSTNAME>'
# Alternatively, store the hostname as an environment secret:
# gh secret set --repo "$REPO" --env production SITE_ADDRESS

gh workflow run cd.yml --repo "$REPO" --ref main
```

Use the existing gate username and `secrets/gate_password` through secure operator
access; do not print credentials in logs. Keep the private key outside the repo
and remove its local copy securely after setup. The owner may approve their own
manual run (`prevent_self_review=false`); approval is still required. Verify
required-reviewer protection is available for the repository's visibility and
GitHub plan before enabling CD; do not proceed without the approval gate.

The server stores at most 50 MiB plus one sentinel byte in a mode-0600 temporary
file under `/opt/parcial_4t`, cleans it on exit, verifies the bundle, and pulls
`main` with `--ff-only`. Divergent history fails instead of rewriting server
history. Oversized bundles fail; if full history exceeds the cap, an operator
must review the transfer design rather than bypassing it. Client SSH commands
are ignored; JSON `deploy.original_command_ignored` records presence only to
avoid logging arbitrary credentials.

The receiver forces `SKIP_PULL=1 BEHIND_PROXY=1` and invokes `deploy-vps.sh`,
which rebuilds only this checkout's Compose project and runs smoke checks.
That helper regenerates `.env` using its existing defaults (including gate user
`demo`); ensure the configured gate credentials match. The runner then checks
`https://<SITE_ADDRESS>/api/telemetry/healthz` using gate Basic Auth. The receiver
logs JSON `deploy.*` progress/failure events; Git and deployment-helper output
retain their existing format. Failure stops the job, without automatic rollback;
a failed build may leave the checkout advanced. Recover through existing
administrator access, preserving volumes and secrets. Temporary runner keys are
shredded even after deployment failure.

Offline validation: see [.github/README.md](../.github/README.md#continuous-deployment).
Live approval, SSH, Docker and public health checks require the orchestrator.

## Dedicated VPS (BEHIND_PROXY=0)

## 1. Harden the server (as root, once)

```sh
adduser deploy && usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh && cp ~/.ssh/authorized_keys /home/deploy/.ssh/ && chown -R deploy:deploy /home/deploy/.ssh
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/; s/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh
ufw default deny incoming && ufw default allow outgoing
ufw allow from <YOUR_PUBLIC_IP> to any port 22 proto tcp
ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
apt update && apt -y upgrade && apt -y install unattended-upgrades git python3
```

Also mirror the same rules in **hPanel → VPS → Firewall** (22 from your IP, 80, 443; nothing else). Grafana, Postgres, Redis and MQTT are never published.

## 2. Docker (as deploy)

```sh
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy && newgrp docker
```

## 3. Deploy

```sh
git clone https://github.com/pacheco20222/parcial_4t.git && cd parcial_4t
SITE_ADDRESS=203-0-113-7.sslip.io bash scripts/deploy-vps.sh
```

The script writes `.env` (prod: Let's Encrypt, ports 80/443, site gate on, `cycle` scenario), runs `bootstrap.sh`, builds and starts everything, and runs the smoke test through the gate.
It sets `COMPOSE_PROFILES=soc-demo` to start `attack-scheduler`: one weighted lab scenario every `ATTACK_INTERVAL_MINUTES` (default 12, minimum 5) with ±30% jitter.

- Site gate (browser login prompt): user `demo`, password in `secrets/gate_password`.
- App users: `admin|supervisor|operator@flood.local`, passwords in `secrets/seed_*_password`.
- SOC: `https://<host>/soc/` (Grafana `admin`, `secrets/grafana_admin_password`).
- Update later: `git pull` is done by re-running the same command.

## 4. Demo helpers

```sh
docker compose up -d simulator                              # cycle scenario from .env
docker compose --profile demo run --rm attack-sim           # SIEM alerts in Grafana
docker compose logs -f telemetry-service ops-service        # live logs
```

## 5. Teardown

Delete the VPS in hPanel (destroys disks, secrets and data). Optionally rotate nothing else — no external credentials are used.

## Infrastructure as code (OpenTofu)

`infra/tofu/` provisions a **new dedicated** Hostinger VPS (SSH key, post-install script, VPS) that bootstraps Docker, ufw and runs `BEHIND_PROXY=0 scripts/deploy-vps.sh`. It must never manage or import the shared VPS. Plan-only until applied by hand; see `infra/tofu/README.md`.

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

# OpenTofu: dedicated Hostinger VPS

> **WARNING: never manage or import the current live server with this code.**
> The existing VPS is **shared** with other production projects. Do NOT run `tofu import`,
> do NOT point this config at it, and never `tofu destroy` against any state that contains it.
> This code only creates a **new, dedicated** VPS and is plan-only until you decide to apply.

## What it creates

- `hostinger_vps_ssh_key`: your admin public key.
- `hostinger_vps_post_install_script`: `cloud-init.sh.tftpl`, run once as root after install.
- `hostinger_vps`: KVM 2 (default), Ubuntu 24.04 (template looked up by name regex), chosen data center.

The post-install script: creates `deploy` user (key-only SSH, root login and passwords disabled), installs Docker + compose plugin, enables ufw (22 from `admin_cidr`, 80, 443), clones the repo to `/opt/parcial_4t`, and runs `BEHIND_PROXY=0 SITE_ADDRESS=<ip-dashes>.sslip.io bash scripts/deploy-vps.sh` (Caddy owns 80/443, Let's Encrypt). The IP is detected on the VPS itself; the `sslip_hostname` output shows the same value. Progress: `/post_install.log` or `docker compose ps` as `deploy`.

**Firewall:** provider `hostinger/hostinger` has no firewall resource. ufw on the host covers it; also mirror the rules by hand in hPanel -> VPS -> Firewall (22 from admin CIDR, 80, 443).

## Cost

A new paid Hostinger subscription (KVM 2, monthly billing by default). Destroy cancels the subscription; check hPanel afterwards.

## Usage (from `infra/tofu`)

```sh
export TF_VAR_hostinger_api_token="$HOSTINGER_API_TOKEN"
export TF_VAR_state_passphrase="<16+ chars, store in a password manager>"
cp terraform.tfvars.example terraform.tfvars   # edit: admin_cidr, ssh_public_key, data_center_id
tofu init
tofu plan -out=tfplan      # review
tofu apply tfplan          # creates and bills a VPS
tofu destroy               # cancels the VPS
```

Find ids: `tofu console` then `data.hostinger_vps_data_centers`, `data.hostinger_vps_plans`, `data.hostinger_vps_templates` (needs a real token).

## State

State holds the root password and the bootstrap script. Keep it local, never commit it (`.gitignore` covers it). State and plan files are encrypted with an AES-GCM key derived from `state_passphrase` (OpenTofu >= 1.7; pinned `~> 1.10.0`). Losing the passphrase means losing the state.

Pinned: OpenTofu `~> 1.10.0`, provider `hostinger/hostinger ~> 0.1.23` (hashes in `.terraform.lock.hcl`).

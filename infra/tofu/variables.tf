variable "hostinger_api_token" {
  description = "Hostinger API token. Set via TF_VAR_hostinger_api_token (e.g. from HOSTINGER_API_TOKEN)."
  type        = string
  sensitive   = true
}

variable "state_passphrase" {
  description = "Passphrase (16+ chars) encrypting state and plan files. Set via TF_VAR_state_passphrase."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.state_passphrase) >= 16
    error_message = "state_passphrase must be at least 16 characters."
  }
}

variable "admin_cidr" {
  description = "CIDR allowed to SSH (port 22), e.g. 203.0.113.7/32. Must not be open to the world."
  type        = string

  validation {
    condition     = can(cidrhost(var.admin_cidr, 0)) && var.admin_cidr != "0.0.0.0/0" && var.admin_cidr != "::/0"
    error_message = "admin_cidr must be a valid CIDR and not 0.0.0.0/0."
  }
}

variable "ssh_public_key" {
  description = "SSH public key installed for root (Hostinger key) and for the deploy user."
  type        = string

  validation {
    condition     = can(regex("^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp[0-9]+) [A-Za-z0-9+/=]+( .*)?$", trimspace(var.ssh_public_key)))
    error_message = "ssh_public_key must be a single-line OpenSSH public key."
  }
}

variable "plan" {
  description = "Hostinger VPS plan id (see data source hostinger_vps_plans). KVM 2 = 2 vCPU / 8 GB."
  type        = string
  default     = "hostingercom-vps-kvm2-usd-1m"
}

variable "data_center_id" {
  description = "Hostinger data center id (see data source hostinger_vps_data_centers)."
  type        = number
}

variable "template_name_regex" {
  description = "Regex matching exactly one OS template name."
  type        = string
  default     = "^Ubuntu 24\\.04"
}

variable "hostname" {
  description = "Optional VPS FQDN. Null lets Hostinger generate one."
  type        = string
  default     = null
}

variable "name_prefix" {
  description = "Prefix for named Hostinger objects (SSH key, script)."
  type        = string
  default     = "parcial4t"
}

variable "repo_url" {
  description = "Repository cloned to /opt/parcial_4t."
  type        = string
  default     = "https://github.com/pacheco20222/parcial_4t"
}

variable "repo_ref" {
  description = "Branch or tag to deploy."
  type        = string
  default     = "main"
}

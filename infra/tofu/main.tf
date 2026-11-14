data "hostinger_vps_templates" "all" {}

locals {
  matching_templates = [
    for t in data.hostinger_vps_templates.all.templates : t if can(regex(var.template_name_regex, t.name))
  ]
  template_id = one(local.matching_templates).id
}

resource "hostinger_vps_ssh_key" "admin" {
  name = "${var.name_prefix}-admin"
  key  = trimspace(var.ssh_public_key)
}

# The provider has no firewall resource: ufw is configured by this script;
# mirror the rules in hPanel -> VPS -> Firewall by hand (see README).
resource "hostinger_vps_post_install_script" "bootstrap" {
  name = "${var.name_prefix}-bootstrap"
  content = templatefile("${path.module}/cloud-init.sh.tftpl", {
    ssh_public_key = trimspace(var.ssh_public_key)
    admin_cidr     = var.admin_cidr
    repo_url       = var.repo_url
    repo_ref       = var.repo_ref
  })
}

resource "hostinger_vps" "this" {
  plan                   = var.plan
  data_center_id         = var.data_center_id
  template_id            = local.template_id
  hostname               = var.hostname
  ssh_key_ids            = [hostinger_vps_ssh_key.admin.id]
  post_install_script_id = hostinger_vps_post_install_script.bootstrap.id
}

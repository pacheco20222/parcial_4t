output "ipv4_address" {
  description = "Public IPv4 of the dedicated VPS."
  value       = hostinger_vps.this.ipv4_address
}

output "sslip_hostname" {
  description = "Hostname Caddy gets a Let's Encrypt cert for (matches the one derived in the bootstrap script)."
  value       = "${replace(hostinger_vps.this.ipv4_address, ".", "-")}.sslip.io"
}

output "url" {
  value = "https://${replace(hostinger_vps.this.ipv4_address, ".", "-")}.sslip.io"
}

output "ssh" {
  value = "ssh deploy@${hostinger_vps.this.ipv4_address}"
}

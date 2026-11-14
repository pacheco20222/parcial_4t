terraform {
  required_version = "~> 1.10.0"

  required_providers {
    hostinger = {
      source  = "hostinger/hostinger"
      version = "~> 0.1.23"
    }
  }
}

provider "hostinger" {
  # Token comes from TF_VAR_hostinger_api_token; never hardcode it.
  api_token = var.hostinger_api_token
}

# Local state holds the root password and the post-install script: encrypt it.
terraform {
  encryption {
    key_provider "pbkdf2" "main" {
      passphrase = var.state_passphrase
    }
    method "aes_gcm" "main" {
      keys = key_provider.pbkdf2.main
    }
    state {
      method   = method.aes_gcm.main
      enforced = true
    }
    plan {
      method   = method.aes_gcm.main
      enforced = true
    }
  }
}

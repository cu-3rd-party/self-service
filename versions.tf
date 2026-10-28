terraform {
  required_version = ">= 1.10.0, < 2.0.0"
  backend "s3" {}
  required_providers {
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.38" }
    postgresql = { source = "cyrilgdn/postgresql", version = "~> 1.25" }
    random     = { source = "hashicorp/random", version = "~> 3.7" }
    cloudflare = { source = "cloudflare/cloudflare", version = "~> 5.0" }
    minio      = { source = "aminueza/minio", version = "~> 3.6" }
  }
  encryption {
    key_provider "pbkdf2" "state" { passphrase = var.state_passphrase }
    method "aes_gcm" "state" { keys = key_provider.pbkdf2.state }
    state {
      method   = method.aes_gcm.state
      enforced = true
    }
    plan {
      method   = method.aes_gcm.state
      enforced = true
    }
  }
}

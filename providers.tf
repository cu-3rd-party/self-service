provider "kubernetes" { config_path = var.kubeconfig }
provider "postgresql" {
  host            = var.postgres_host
  port            = var.postgres_port
  username        = var.postgres_username
  password        = var.postgres_password
  database        = "postgres"
  sslmode         = "require"
  connect_timeout = 15
  superuser       = true
}
provider "minio" {
  minio_server   = var.s3_server
  minio_user     = var.s3_access_key
  minio_password = var.s3_secret_key
  minio_ssl      = true
}
provider "litellm" {
  api_base = var.litellm_url
  api_key  = local.litellm_master_key
}

# Authentication is read from CLOUDFLARE_API_TOKEN on nxs, never Actions.
provider "cloudflare" {}

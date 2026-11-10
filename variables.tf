variable "state_passphrase" {
  type      = string
  sensitive = true
}
variable "kubeconfig" {
  type    = string
  default = "/etc/rancher/k3s/k3s.yaml"
}
variable "postgres_host" { type = string }
variable "postgres_port" {
  type    = number
  default = 5432
}
variable "postgres_password" {
  type      = string
  sensitive = true
}
variable "postgres_username" {
  type    = string
  default = "postgres"
}
variable "s3_server" {
  type    = string
  default = "storage.cu3rd.ru"
}
variable "s3_access_key" {
  type      = string
  sensitive = true
}
variable "s3_secret_key" {
  type      = string
  sensitive = true
}
variable "litellm_url" {
  description = "Public LiteLLM endpoint (project ai-gateway); apps reach it through cluster Traefik."
  type        = string
  default     = "https://ai.cu3rd.ru"
}
variable "litellm_key_secret" {
  description = "Kubernetes Secret (namespace/name) with LITELLM_MASTER_KEY, delivered with the ai-gateway app; read only while a project enables ai."
  type        = string
  default     = "cu3rd-ai-gateway-prod/ai-gateway-prod-litellm-env"
}
variable "chart_revision" {
  description = "Immutable commit containing the reviewed application chart."
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for cu3rd.ru; configured outside Git on nxs."
  type        = string
  default     = ""
}
# SSH-шлюз ssh.cu3rd.ru:8222 (homelab ssh-gateway/). Публичная часть секрета upstream-key:
# её чарт кладёт в authorized_keys приложений с блоком ssh.
variable "ssh_gateway_namespace" {
  type    = string
  default = "ssh-gateway"
}
variable "ssh_gateway_public_key" {
  type    = string
  default = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPOWcaWv0dW4gz7c6HHvLvox69QhCzUg9O9LuWjnRVTY self-service-ssh-gateway"
}

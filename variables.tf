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
  default = "s3.iamamaev.ru"
}
variable "s3_access_key" {
  type      = string
  sensitive = true
}
variable "s3_secret_key" {
  type      = string
  sensitive = true
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

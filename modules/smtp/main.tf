terraform {
  required_providers {
    kubernetes = { source = "hashicorp/kubernetes" }
  }
}
variable "name" { type = string }
variable "namespace" { type = string }
variable "mailbox" {
  type = object({
    host     = string
    port     = number
    user     = string
    password = string
  })
  sensitive = true
}
variable "config" {
  type = object({
    enabled         = bool
    targetEnvPrefix = optional(string, "SMTP_")
  })
}
resource "kubernetes_secret_v1" "smtp" {
  metadata {
    name      = "${var.name}-smtp"
    namespace = var.namespace
  }
  data = {
    "${var.config.targetEnvPrefix}HOST"     = var.mailbox.host
    "${var.config.targetEnvPrefix}PORT"     = tostring(var.mailbox.port)
    "${var.config.targetEnvPrefix}USER"     = var.mailbox.user
    "${var.config.targetEnvPrefix}PASSWORD" = var.mailbox.password
  }
}

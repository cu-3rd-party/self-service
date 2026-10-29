terraform {
  required_providers {
    litellm    = { source = "registry.terraform.io/berriai/litellm" }
    kubernetes = { source = "hashicorp/kubernetes" }
  }
}
variable "name" { type = string }
variable "namespace" { type = string }
variable "project" { type = string }
variable "env" { type = string }
variable "base_url" { type = string }
variable "config" {
  type = object({
    enabled         = bool
    targetEnvPrefix = optional(string, "AI_")
    model           = optional(string)
    models          = optional(list(string), [])
    budgetUsd       = optional(number)
    budgetPeriod    = optional(string, "30d")
    rpm             = optional(number)
    tpm             = optional(number)
  })
}
resource "litellm_key" "app" {
  key_alias       = "ss-${var.name}"
  models          = var.config.models
  max_budget      = var.config.budgetUsd
  budget_duration = var.config.budgetUsd == null ? null : var.config.budgetPeriod
  rpm_limit       = var.config.rpm
  tpm_limit       = var.config.tpm
  metadata = {
    managed_by  = "self-service"
    project     = var.project
    environment = var.env
  }
}
resource "kubernetes_secret_v1" "ai" {
  metadata {
    name      = "${var.name}-ai"
    namespace = var.namespace
  }
  data = merge({
    "${var.config.targetEnvPrefix}API_KEY"  = litellm_key.app.key
    "${var.config.targetEnvPrefix}BASE_URL" = var.base_url
  }, var.config.model == null ? {} : { "${var.config.targetEnvPrefix}MODEL" = var.config.model })
}

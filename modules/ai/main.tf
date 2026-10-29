terraform {
  required_providers {
    litellm    = { source = "registry.terraform.io/berriai/litellm" }
    kubernetes = { source = "hashicorp/kubernetes" }
    random     = { source = "hashicorp/random" }
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
# `key` у litellm_key write-only: провайдер принимает его, но не возвращает и не хранит
# (litellm_key.*.key всегда null), поэтому значение ключа генерируем сами и отдаём и ему, и Secret.
resource "random_password" "key" {
  length  = 48
  special = false
}
locals {
  api_key = "sk-${random_password.key.result}"
  # Поколение ключа: увеличьте, чтобы перевыпустить ключ. Алиас в LiteLLM уникален, поэтому он
  # меняется вместе с поколением, и старый ключ удаляется параллельно с созданием нового.
  key_generation = 2
}
resource "litellm_key" "issued" {
  key             = local.api_key
  key_alias       = "ss-${var.name}-${local.key_generation}"
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
    "${var.config.targetEnvPrefix}API_KEY"  = local.api_key
    "${var.config.targetEnvPrefix}BASE_URL" = var.base_url
  }, var.config.model == null ? {} : { "${var.config.targetEnvPrefix}MODEL" = var.config.model })
  # Под не должен получить ключ раньше, чем LiteLLM его признает.
  depends_on = [litellm_key.issued]
}

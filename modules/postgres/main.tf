terraform {
  required_providers {
    postgresql = { source = "cyrilgdn/postgresql" }
    random     = { source = "hashicorp/random" }
    kubernetes = { source = "hashicorp/kubernetes" }
  }
}
variable "name" { type = string }
variable "namespace" { type = string }
variable "config" {
  type = object({
    enabled   = bool
    targetEnv = optional(string, "DATABASE_URL")
    format    = optional(string, "url")
  })
}
locals {
  database = replace(var.name, "-", "_")
  host     = "pg-grm-pooler-rw.postgres.svc.cluster.local"
  url      = "postgresql://${local.database}:${random_password.db.result}@${local.host}:5432/${local.database}"
  npgsql   = "Host=${local.host};Port=5432;Database=${local.database};Username=${local.database};Password=${random_password.db.result};No Reset On Close=true"
}
resource "random_password" "db" {
  length  = 48
  special = false
  lifecycle { prevent_destroy = true }
}
resource "postgresql_role" "app" {
  name                = local.database
  login               = true
  password            = random_password.db.result
  superuser           = false
  create_database     = false
  create_role         = false
  replication         = false
  skip_reassign_owned = true
  lifecycle { prevent_destroy = true }
}
resource "postgresql_database" "app" {
  name  = local.database
  owner = postgresql_role.app.name
  lifecycle { prevent_destroy = true }
}
resource "postgresql_grant" "public" {
  database    = postgresql_database.app.name
  role        = "public"
  object_type = "database"
  privileges  = []
}
resource "kubernetes_secret_v1" "db" {
  metadata {
    name      = "${var.name}-db"
    namespace = var.namespace
  }
  data       = { (var.config.targetEnv) = var.config.format == "npgsql" ? local.npgsql : local.url }
  depends_on = [postgresql_grant.public]
}

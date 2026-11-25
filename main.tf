locals {
  projects = { for f in fileset(path.module, "projects/*.yaml") : trimsuffix(basename(f), ".yaml") => yamldecode(file("${path.module}/${f}")) }
  environments = merge({}, [for name, p in local.projects : {
    for env, config in p.envs : "${name}-${env}" => merge(config, { project = name, env = env })
  }]...)
}
module "project" {
  source         = "./modules/project"
  for_each       = local.environments
  name           = each.key
  config         = each.value
  root           = path.module
  chart_revision = var.chart_revision
  ssh_gateway    = { namespace = var.ssh_gateway_namespace, public_key = var.ssh_gateway_public_key, key_secret = "upstream-key" }
  extra_egress   = try(each.value.extraEgress, [])
  extra_ingress  = try(each.value.extraIngress, [])
}
module "postgres" {
  source    = "./modules/postgres"
  for_each  = { for k, e in local.environments : k => e if try(e.postgres.enabled, false) }
  name      = each.key
  namespace = module.project[each.key].namespace
  config    = each.value.postgres
}
module "s3" {
  source    = "./modules/s3"
  for_each  = { for k, e in local.environments : k => e if try(e.s3.enabled, false) }
  name      = each.key
  namespace = module.project[each.key].namespace
  config    = each.value.s3
}
# The LiteLLM admin key is already in the cluster (delivered with ai-gateway), so nothing is configured on nxs.
data "kubernetes_secret_v1" "litellm" {
  count = length([for e in local.environments : 1 if try(e.ai.enabled, false)]) > 0 ? 1 : 0
  metadata {
    namespace = split("/", var.litellm_key_secret)[0]
    name      = split("/", var.litellm_key_secret)[1]
  }
}
locals {
  litellm_master_key = length(data.kubernetes_secret_v1.litellm) > 0 ? data.kubernetes_secret_v1.litellm[0].data["LITELLM_MASTER_KEY"] : ""
}
module "ai" {
  source    = "./modules/ai"
  for_each  = { for k, e in local.environments : k => e if try(e.ai.enabled, false) }
  name      = each.key
  namespace = module.project[each.key].namespace
  project   = each.value.project
  env       = each.value.env
  base_url  = "${var.litellm_url}/v1"
  config    = each.value.ai
}
locals {
  smtp_environments = { for k, e in local.environments : k => e.smtp if try(e.smtp.enabled, false) }
}
resource "terraform_data" "smtp_configuration" {
  input = sort(keys(local.smtp_environments))
  lifecycle {
    precondition {
      condition     = length(local.smtp_environments) == 0 || var.smtp_password != ""
      error_message = "smtp requires TF_VAR_smtp_password in /etc/cu3rd-self-service/runtime.env on nxs."
    }
  }
}
module "smtp" {
  source     = "./modules/smtp"
  for_each   = local.smtp_environments
  name       = each.key
  namespace  = module.project[each.key].namespace
  mailbox    = { host = var.smtp_host, port = var.smtp_port, user = var.smtp_user, password = var.smtp_password }
  config     = each.value
  depends_on = [terraform_data.smtp_configuration]
}

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

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

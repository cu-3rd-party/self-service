locals {
  ingress_domains = flatten([for env in values(local.environments) : [
    for app in values(try(env.apps, {})) : [
      for domain in concat([for route in try(app.ingress, []) : route.domain], try(app.host, "") != "" ? [app.host] : []) : {
        domain = domain
        zone   = try(env.zone, "nxs")
      }
    ]
  ]])
  # Multiple paths/apps may share a domain within an environment; one A record.
  domain_zones = { for route in local.ingress_domains : route.domain => route.zone... }
  zone_addresses = {
    nxs = "85.192.48.255"
    grm = "109.120.137.209"
    # akh (РФ) без своего Traefik: сайты зоны akh входят через Traefik nxs,
    # дальше до пода по туннелю (homelab hosts/awgk).
    akh = "85.192.48.255"
    # nki: своего Traefik нет — вход через Traefik nxs
    nki = "85.192.48.255"
    # xmsk: своего Traefik нет — вход через Traefik nxs
    xmsk = "85.192.48.255"
    # xgrm: своего Traefik нет — вход через Traefik nxs
    xgrm = "85.192.48.255"
  }
}
resource "terraform_data" "dns_configuration" {
  input = sort(keys(local.domain_zones))
  lifecycle {
    precondition {
      condition     = length(local.domain_zones) == 0 || var.cloudflare_zone_id != ""
      error_message = "Ingress requires TF_VAR_cloudflare_zone_id and CLOUDFLARE_API_TOKEN in /etc/cu3rd-self-service/cloudflare.env on nxs."
    }
  }
}
resource "cloudflare_dns_record" "app" {
  for_each   = var.cloudflare_zone_id != "" ? local.domain_zones : {}
  zone_id    = var.cloudflare_zone_id
  name       = each.key
  type       = "A"
  content    = local.zone_addresses[each.value[0]]
  ttl        = 120
  proxied    = false
  comment    = "Managed by cu3rd/self-service; TLS terminates at Traefik"
  depends_on = [terraform_data.dns_configuration]
}

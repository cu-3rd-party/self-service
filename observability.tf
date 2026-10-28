resource "kubernetes_config_map_v1" "self_service_dashboard" {
  metadata {
    name      = "dashboard-cu3rd-self-service"
    namespace = "monitoring"
    labels    = { grafana_dashboard = "1" }
  }
  data = { "cu3rd-self-service.json" = file("${path.module}/observability/dashboard.json") }
}

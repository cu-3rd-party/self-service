terraform {

  required_providers {
    kubernetes = {
      source = "hashicorp/kubernetes"
    }
  }
}
variable "name" {
  type = string
}
variable "config" {
  type = any
}
variable "root" {
  type = string
}
variable "chart_revision" {
  type = string
}
locals {

  namespace = "cu3rd-${var.name}"
  apps = try(var.config.apps, {
  })
  deliveries = {
    for name, app in local.apps : name => try(yamldecode(file("${var.root}/deployments/${var.config.project}/${var.config.env}/${name}.yaml")), {
    })
  }
  metrics_ports = toset([for app in values(local.apps) : try(coalesce(try(app.metrics.port, null), try(app.port, null), try(app.ingress[0].targetPort, null)), 9090) if try(app.metrics.enabled, false)])
  resource_secrets = concat(
    try(var.config.postgres.enabled, false) ? ["${var.name}-db"] : [],
    try(var.config.s3.enabled, false) ? ["${var.name}-s3"] : []
  )
}
resource "kubernetes_namespace_v1" "project" {

  metadata {

    name = local.namespace
    labels = {

      "cu3rd.ru/project"                           = var.config.project
      "cu3rd.ru/env"                               = var.config.env
      "pod-security.kubernetes.io/enforce"         = "restricted"
      "pod-security.kubernetes.io/enforce-version" = "latest"

    }

  }
}
resource "kubernetes_resource_quota_v1" "project" {

  metadata {

    name      = "project"
    namespace = kubernetes_namespace_v1.project.metadata[0].name

  }
  spec {

    hard = {

      "limits.cpu"             = try(var.config.quota.cpu, "2")
      "limits.memory"          = try(var.config.quota.memory, "4Gi")
      "requests.storage"       = try(var.config.quota.storage, "5Gi")
      "pods"                   = "20"
      "services"               = "10"
      "persistentvolumeclaims" = "10"

    }

  }
}
resource "kubernetes_limit_range_v1" "project" {

  metadata {

    name      = "defaults"
    namespace = kubernetes_namespace_v1.project.metadata[0].name

  }
  spec {

    limit {

      type = "Container"
      default = {
        cpu = "500m", memory = "512Mi"
      }
      default_request = {
        cpu = "50m", memory = "64Mi"
      }

    }

  }
}
resource "kubernetes_network_policy_v1" "project" {

  metadata {

    name      = "isolate"
    namespace = kubernetes_namespace_v1.project.metadata[0].name

  }
  spec {

    pod_selector {
    }
    policy_types = ["Ingress", "Egress"]
    ingress {
      from {
        pod_selector {
        }
      }
    }
    ingress {

      from {

        namespace_selector {
          match_labels = {
            "kubernetes.io/metadata.name" = "kube-system"
          }
        }
        pod_selector {
          match_labels = {
            "app.kubernetes.io/name" = "traefik"
          }
        }

      }

    }
    dynamic "ingress" {
      for_each = length(local.metrics_ports) > 0 ? [1] : []
      content {
        from {
          namespace_selector { match_labels = { "kubernetes.io/metadata.name" = "monitoring" } }
          pod_selector { match_labels = { "app.kubernetes.io/name" = "prometheus" } }
        }
        dynamic "ports" {
          for_each = local.metrics_ports
          content {
            port     = tostring(ports.value)
            protocol = "TCP"
          }
        }
      }
    }
    egress {
      to {
        pod_selector {
        }
      }
    }
    egress {

      to {

        namespace_selector {
          match_labels = {
            "kubernetes.io/metadata.name" = "kube-system"
          }
        }
        pod_selector {
          match_labels = {
            "k8s-app" = "kube-dns"
          }
        }

      }
      ports {
        port     = "53"
        protocol = "UDP"

      }
      ports {
        port     = "53"
        protocol = "TCP"

      }

    }
    egress {

      to {
        namespace_selector {
          match_labels = {
            "kubernetes.io/metadata.name" = "postgres"
          }
        }
      }
      ports {
        port     = "5432"
        protocol = "TCP"

      }

    }
    egress {

      to {
        namespace_selector {
          match_labels = {
            "kubernetes.io/metadata.name" = "s3"
          }
        }
      }
      ports {
        port     = "9000"
        protocol = "TCP"

      }

    }
    egress {

      # Cluster-hosted sites resolve to node IPs (blocked below); hostPort 80/443
      # is DNATed to Traefik's container ports, so allow only those.
      to {

        namespace_selector {
          match_labels = {
            "kubernetes.io/metadata.name" = "kube-system"
          }
        }
        pod_selector {
          match_labels = {
            "app.kubernetes.io/name" = "traefik"
          }
        }

      }
      ports {
        port     = "8000"
        protocol = "TCP"

      }
      ports {
        port     = "8443"
        protocol = "TCP"

      }

    }
    egress {

      to {
        ip_block {

          cidr   = "0.0.0.0/0"
          except = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16"]

        }
      }
      ports {
        port     = "443"
        protocol = "TCP"

      }
      ports {
        port     = "80"
        protocol = "TCP"

      }

    }

  }
}
resource "kubernetes_manifest" "argo_project" {

  manifest = {

    apiVersion = "argoproj.io/v1alpha1"
    kind       = "AppProject"
    metadata = {
      name = "cu3rd-${var.name}", namespace = "argocd"
    }
    spec = {

      sourceRepos = ["https://git.cu3rd.ru/cu3rd/self-service.git"]
      destinations = [{ server = "https://kubernetes.default.svc", namespace = local.namespace
      }]
      clusterResourceWhitelist = []
      namespaceResourceWhitelist = [
        {
          group = "apps", kind = "Deployment"
        },
        {
          group = "", kind = "Service"
        },
        {
          group = "", kind = "ConfigMap"
        },
        {
          group = "", kind = "PersistentVolumeClaim"
        },
        {
          group = "", kind = "Secret"
        },
        {
          group = "bitnami.com", kind = "SealedSecret"
        },
        {
          group = "networking.k8s.io", kind = "Ingress"
        },
        {
          group = "monitoring.coreos.com", kind = "PodMonitor"
        },
        {
          group = "traefik.io", kind = "Middleware"
        }
      ]

    }

  }
}
resource "kubernetes_manifest" "application" {

  for_each = {
    for k, a in local.apps : k => a if length(try(a.secrets, {
      })) + length(try(a.variables, {
    })) == 0 || length(local.deliveries[k]) > 0
  }
  manifest = {

    apiVersion = "argoproj.io/v1alpha1"
    kind       = "Application"
    metadata = {
      name       = "cu3rd-${var.name}-${each.key}", namespace = "argocd"
      finalizers = ["resources-finalizer.argocd.argoproj.io"]
    }
    spec = {

      project = kubernetes_manifest.argo_project.manifest.metadata.name
      source = {

        repoURL        = "https://git.cu3rd.ru/cu3rd/self-service.git"
        targetRevision = var.chart_revision
        path           = "charts/app"
        helm = {

          releaseName = "${var.name}-${each.key}"
          values = yamlencode(merge(try(each.value.values, {
            }), {

            image = {
              repository = each.value.image, tag = try(local.deliveries[each.key].tag, each.value.tag, "latest")
            }
            env = try(local.deliveries[each.key].env, {
            })
            sealedEnv = try(local.deliveries[each.key].sealedEnv, {
            })
            secretRefs     = local.resource_secrets
            configRevision = sha256(jsonencode(local.deliveries[each.key]))
            nodeSelector = {
              "homelab/site" = try(var.config.zone, "nxs")
            }
            ingress = {
              enabled = try(each.value.host, "") != "", host = try(each.value.host, ""), paths = try(each.value.paths, ["/"])
            }
            routes      = try(each.value.ingress, [])
            selfService = { project = var.config.project, env = var.config.env, application = each.key }
            metrics     = merge({ enabled = false, path = "/metrics", interval = "30s", port = try(coalesce(try(each.value.port, null), try(each.value.ingress[0].targetPort, null)), 9090) }, try(each.value.metrics, {}))
            port        = try(coalesce(try(each.value.port, null), try(each.value.ingress[0].targetPort, null)), null)

          }))

        }

      }
      destination = {
        server = "https://kubernetes.default.svc", namespace = local.namespace
      }
      syncPolicy = {

        automated = {
          prune = true, selfHeal = true
        }
        retry = {
          limit = 10, backoff = {
            duration = "15s", maxDuration = "3m"
          }
        }

      }

    }

  }
  depends_on = [kubernetes_resource_quota_v1.project, kubernetes_limit_range_v1.project, kubernetes_network_policy_v1.project]
}
output "namespace" {
  value = kubernetes_namespace_v1.project.metadata[0].name
}

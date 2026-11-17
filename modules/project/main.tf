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
variable "extra_egress" {
  description = "Дополнительные egress-правила isolate: [{cidr, ports}]"
  type = list(object({
    cidr  = string
    ports = list(number)
  }))
  default = []
}

variable "ssh_gateway" {
  type = object({ namespace = string, public_key = string, key_secret = string })
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
  ssh_apps      = { for name, app in local.apps : name => app.ssh if try(app.ssh, null) != null }
  vms           = try(var.config.vms, {})
  ssh_vms       = { for name, vm in local.vms : name => vm.ssh if try(vm.ssh, null) != null }
  ssh_ports     = toset(concat([for ssh in values(local.ssh_apps) : try(ssh.port, 2222)], length(local.ssh_vms) > 0 ? [22] : []))
  resource_secrets = concat(
    try(var.config.postgres.enabled, false) ? ["${var.name}-db"] : [],
    try(var.config.s3.enabled, false) ? ["${var.name}-s3"] : [],
    try(var.config.ai.enabled, false) ? ["${var.name}-ai"] : [],
    try(var.config.smtp.enabled, false) ? ["${var.name}-smtp"] : []
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

    # services: на HTTP-приложение два Service (свой и маршрута) плюс запас под
    # временные Service солверов cert-manager: без него пятое приложение выбирало
    # всю квоту и сертификат последнего домена не выпускался
    hard = {

      "limits.cpu"             = try(var.config.quota.cpu, "2")
      "limits.memory"          = try(var.config.quota.memory, "4Gi")
      "requests.storage"       = try(var.config.quota.storage, "5Gi")
      "pods"                   = "20"
      "services"               = tostring(max(10, 2 * length(local.apps) + 5))
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
    dynamic "ingress" {
      for_each = length(local.ssh_ports) > 0 ? [1] : []
      content {
        from {
          namespace_selector { match_labels = { "kubernetes.io/metadata.name" = var.ssh_gateway.namespace } }
          pod_selector { match_labels = { "app.kubernetes.io/name" = "sshpiper" } }
        }
        dynamic "ports" {
          for_each = local.ssh_ports
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
    dynamic "egress" {
      for_each = var.extra_egress
      iterator = extra
      content {
        to {
          ip_block {
            cidr = extra.value.cidr
          }
        }
        dynamic "ports" {
          for_each = extra.value.ports
          content {
            port     = tostring(ports.value)
            protocol = "TCP"
          }
        }
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
        },
        {
          group = "kubevirt.io", kind = "VirtualMachine"
        }
      ]

    }

  }
}
# Зона, в которой окружение жило при первом apply. Тома local-path привязаны
# к диску узла, поэтому при смене зоны PVC получает новое имя с суффиксом
# зоны: новый том создаётся на новом узле, старый Argo удаляет (prune).
resource "terraform_data" "storage_zone" {
  input = try(var.config.zone, "nxs")
  lifecycle { ignore_changes = [input] }
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
            persistenceSuffix = try(var.config.zone, "nxs") == terraform_data.storage_zone.output ? "" : "-${try(var.config.zone, "nxs")}"
            ingress = {
              enabled = try(each.value.host, "") != "", host = try(each.value.host, ""), paths = try(each.value.paths, ["/"])
            }
            routes      = try(each.value.ingress, [])
            selfService = { project = var.config.project, env = var.config.env, application = each.key }
            metrics     = merge({ enabled = false, path = "/metrics", interval = "30s", port = try(coalesce(try(each.value.port, null), try(each.value.ingress[0].targetPort, null)), 9090) }, try(each.value.metrics, {}))
            port        = try(coalesce(try(each.value.port, null), try(each.value.ingress[0].targetPort, null)), null)
            ssh         = { enabled = contains(keys(local.ssh_apps), each.key), port = try(each.value.ssh.port, 2222), authorizedKeys = var.ssh_gateway.public_key }

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
# Маршрут шлюза ssh.cu3rd.ru:8222 (homelab ssh-gateway/): логин и ключи людей -> sshd приложения.
# Pipe лежит в namespace шлюза, поэтому приватный ключ шлюза в namespace проекта не попадает.
resource "kubernetes_manifest" "ssh_pipe" {
  for_each = merge(local.ssh_apps, { for name, ssh in local.ssh_vms : name => merge(ssh, { port = 22 }) })
  manifest = {
    apiVersion = "sshpiper.com/v1beta1"
    kind       = "Pipe"
    metadata = {
      name      = try(each.value.login, "${var.name}-${each.key}")
      namespace = var.ssh_gateway.namespace
      labels = {
        "cu3rd.ru/managed-by"  = "self-service"
        "cu3rd.ru/project"     = var.config.project
        "cu3rd.ru/env"         = var.config.env
        "cu3rd.ru/application" = each.key
      }
    }
    spec = {
      from = [{
        username             = try(each.value.login, "${var.name}-${each.key}")
        authorized_keys_data = base64encode("${join("\n", each.value.authorizedKeys)}\n")
      }]
      to = {
        host               = "${var.name}-${each.key}-ssh.${local.namespace}.svc.cluster.local:${try(each.value.port, 2222)}"
        username           = each.value.user
        private_key_secret = { name = var.ssh_gateway.key_secret }
      }
    }
  }
}
output "namespace" {
  value = kubernetes_namespace_v1.project.metadata[0].name
}
# Виртуальные машины KubeVirt (vms в проекте): только зоны с /dev/kvm, проверяет scripts/config.py.
resource "kubernetes_manifest" "vm_application" {
  for_each = local.vms
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
        path           = "charts/vm"
        helm = {
          releaseName = "${var.name}-${each.key}"
          values = yamlencode({
            os           = try(each.value.os, "alpine-3.24")
            cpu          = try(each.value.cpu, 1)
            memory       = try(each.value.memory, "512Mi")
            disk         = try(each.value.disk, "2Gi")
            nodeSelector = { "homelab/site" = try(var.config.zone, "nxs") }
            ssh          = { enabled = contains(keys(local.ssh_vms), each.key), user = try(each.value.ssh.user, "vm"), authorizedKeys = var.ssh_gateway.public_key }
            selfService  = { project = var.config.project, env = var.config.env, application = each.key }
          })
        }
      }
      destination = {
        server = "https://kubernetes.default.svc", namespace = local.namespace
      }
      syncPolicy = {
        automated = { prune = true, selfHeal = true }
        retry     = { limit = 10, backoff = { duration = "15s", maxDuration = "3m" } }
      }
    }
  }
}

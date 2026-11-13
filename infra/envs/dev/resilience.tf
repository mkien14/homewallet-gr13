# Opt-in controls for the existing stack, preserving names and data. Enabling
# ECS scaling requires the documented state moves, never service replacement.
variable "resilience_hardening_enabled" {
  type    = bool
  default = false
}
variable "resilience_apply_immediately" {
  type    = bool
  default = false
}
variable "enable_api_service_discovery" {
  type    = bool
  default = false
  validation {
    condition     = !var.enable_api_service_discovery || (var.enable_api_https_gateway && (var.application_origin_verification_enabled || var.application_hardening_enabled))
    error_message = "Direct ECS integration requires HTTPS gateway and application origin verification."
  }
}
variable "application_origin_verification_enabled" {
  type    = bool
  default = false
}

resource "aws_service_discovery_private_dns_namespace" "api" {
  count = var.enable_api_service_discovery ? 1 : 0
  name  = "homewallet-api.internal"
  vpc   = module.network.vpc_id
}

resource "aws_service_discovery_service" "api" {
  count = var.enable_api_service_discovery ? 1 : 0
  name  = "api"
  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.api[0].id
    dns_records {
      ttl  = 10
      type = "SRV"
    }
    routing_policy = "MULTIVALUE"
  }
  health_check_custom_config {
    failure_threshold = 1
  }
}

locals {
  prefix     = var.name == "homewallet-dev" ? "hw" : var.name
  log_prefix = var.name == "homewallet-dev" ? "/ecs/hw-" : "/ecs/${var.name}/"
}

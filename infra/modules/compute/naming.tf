locals {
  # Preserve every deployed DEV identity, including callers predating prefixes.
  legacy     = var.name == "homewallet-dev"
  prefix     = local.legacy ? "hw" : var.name
  log_prefix = local.legacy ? "/ecs/hw-" : "/ecs/${var.name}/"
}

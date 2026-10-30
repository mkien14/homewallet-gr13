resource "random_password" "auth_token" {
  length  = 48
  special = false
}

resource "aws_secretsmanager_secret" "auth_token" {
  name                    = "${var.name}/redis-auth-token"
  description             = "Redis AUTH token for the HomeWallet API"
  recovery_window_in_days = 7

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_secretsmanager_secret_version" "auth_token" {
  secret_id     = aws_secretsmanager_secret.auth_token.id
  secret_string = random_password.auth_token.result
}

resource "aws_elasticache_subnet_group" "this" {
  name        = "${var.name}-redis-subnets"
  subnet_ids  = var.subnet_ids
  description = "Private subnets for HomeWallet Redis"
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id = "${var.name}-redis"
  description          = "HomeWallet dev dashboard cache"

  engine               = "redis"
  engine_version       = "7.1"
  node_type            = "cache.t4g.micro"
  parameter_group_name = "default.redis7"
  port                 = 6379

  num_cache_clusters         = 1
  automatic_failover_enabled = false
  multi_az_enabled           = false

  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [var.security_group_id]

  transit_encryption_enabled = true
  transit_encryption_mode    = "required"
  at_rest_encryption_enabled = true
  auth_token                 = random_password.auth_token.result

  apply_immediately        = true
  snapshot_retention_limit = 0
}

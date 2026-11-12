output "endpoint_address" {
  value = aws_elasticache_replication_group.this.primary_endpoint_address
}

output "port" {
  value = aws_elasticache_replication_group.this.port
}
output "replication_group_id" { value = aws_elasticache_replication_group.this.id }
output "member_cluster_ids" { value = sort(tolist(aws_elasticache_replication_group.this.member_clusters)) }

output "auth_token_secret_arn" {
  value = aws_secretsmanager_secret.auth_token.arn
}

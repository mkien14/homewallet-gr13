output "vpc_id" { value = module.network.vpc_id }
output "public_subnet_ids" { value = module.network.public_subnet_ids }
output "app_subnet_ids" { value = module.network.app_subnet_ids }
output "data_subnet_ids" { value = module.network.data_subnet_ids }
output "sg_ids" { value = module.network.sg_ids }
output "ecr_url" { value = module.ecr.repository_url }
output "alb_dns_name" { value = module.compute.alb_dns_name }
output "db_address" { value = module.data.address }
output "redis_endpoint" { value = module.cache.endpoint_address }
output "redis_auth_token_secret_arn" { value = module.cache.auth_token_secret_arn }
output "cognito_user_pool_id" { value = module.cognito.user_pool_id }
output "cognito_spa_client_id" { value = module.cognito.spa_client_id }
output "cognito_dev_client_id" { value = module.cognito.dev_client_id }
output "cognito_issuer" { value = module.cognito.issuer }
output "cognito_jwks_uri" { value = module.cognito.jwks_uri }
output "cognito_hosted_ui" { value = module.cognito.hosted_ui_base }
output "receipts_bucket" { value = module.storage.bucket_name }
output "queue_url" {
  value = module.queue.queue_url
}

output "queue_arn" {
  value = module.queue.queue_arn
}

output "dlq_url" {
  value = module.queue.dlq_url
}

output "dlq_arn" {
  value = module.queue.dlq_arn
}

output "worker_service_name" {
  value = module.compute.worker_service_name
}

output "worker_task_definition_arn" {
  value = module.compute.worker_task_definition_arn
}

output "scheduled_jobs_task_definition_arn" {
  value = module.compute.jobs_task_definition_arn
}

output "scheduled_job_names" {
  value = module.compute.scheduled_job_names
}

output "frontend_bucket" {
  value = module.frontend.bucket_id
}

output "cloudfront_url" {
  value = module.edge.url
}

output "cloudfront_distribution_id" {
  value = module.edge.distribution_id
}

output "api_https_origin" {
  value = var.enable_api_https_gateway ? module.api_https[0].origin_domain_name : null
}

output "api_task_definition_arn" {
  value = module.compute.api_task_definition_arn
}


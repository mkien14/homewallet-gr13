terraform {
  required_version = ">= 1.10"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.80" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
  backend "s3" {
    # Separate bucket: legacy DEV collaborators can read every key in DEV bucket.
    bucket       = "hw-tfstate-homewallet-prod-gr13"
    key          = "prod/terraform.tfstate"
    region       = "ap-southeast-1"
    encrypt      = true
    use_lockfile = true
  }
}
provider "aws" {
  region              = "ap-southeast-1"
  allowed_account_ids = [var.expected_account_id]
  default_tags { tags = { project = "homewallet", env = "prod" } }
}
provider "aws" {
  alias               = "us_east_1"
  region              = "us-east-1"
  allowed_account_ids = [var.expected_account_id]
  default_tags { tags = { project = "homewallet", env = "prod" } }
}
locals {
  name  = "homewallet-prod"
  image = "${module.ecr.repository_url}@${var.release_digest}"
  db_environment = {
    DB_HOST   = module.data.address, DB_PORT = "3306", DB_NAME = "homewallet"
    DB_SSL_CA = "/etc/ssl/rds-global-bundle.pem", AWS_REGION = "ap-southeast-1"
  }
  db_secrets = {
    DB_USER     = "${aws_secretsmanager_secret.runtime.arn}:username::"
    DB_PASSWORD = "${aws_secretsmanager_secret.runtime.arn}:password::"
  }
}
module "network" {
  source              = "../../modules/network"
  name                = local.name
  cidr                = "10.1.0.0/16"
  azs                 = ["ap-southeast-1a", "ap-southeast-1b"]
  public_subnet_cidrs = ["10.1.0.0/24", "10.1.1.0/24"]
  app_subnet_cidrs    = ["10.1.10.0/24", "10.1.11.0/24"]
  data_subnet_cidrs   = ["10.1.20.0/24", "10.1.21.0/24"]
  nat_gateway_per_az  = true
  origin_https        = true
}
module "ecr" {
  source     = "../../modules/ecr"
  name       = "homewallet-prod-backend"
  production = true
}
module "data" {
  source                     = "../../modules/data"
  name                       = local.name
  data_subnet_ids            = module.network.data_subnet_ids
  sg_db_id                   = module.network.sg_ids.db
  instance_class             = var.db_instance_class
  engine_version             = var.db_engine_version
  multi_az                   = true
  deletion_protection        = true
  skip_final_snapshot        = false
  final_snapshot_identifier  = var.final_snapshot_identifier
  backup_retention           = 14
  backup_window              = "18:00-19:00"
  maintenance_window         = "sun:20:00-sun:21:00"
  auto_minor_version_upgrade = false
  apply_immediately          = false
  copy_tags_to_snapshot      = true
  delete_automated_backups   = false
}
module "cache" {
  source                     = "../../modules/cache"
  name                       = local.name
  subnet_ids                 = module.network.data_subnet_ids
  security_group_id          = module.network.sg_ids.cache
  auth_secret_name           = "hw/prod/redis-auth-token"
  num_cache_clusters         = 2
  automatic_failover_enabled = true
  multi_az_enabled           = true
  preferred_azs              = ["ap-southeast-1a", "ap-southeast-1b"]
  snapshot_retention_limit   = 7
  apply_immediately          = false
}
resource "aws_secretsmanager_secret" "runtime" {
  name                    = "hw/prod/db-runtime"
  recovery_window_in_days = 30
  lifecycle { prevent_destroy = true }
}
resource "aws_secretsmanager_secret" "gemini" {
  name                    = "hw/prod/gemini-api-key"
  recovery_window_in_days = 30
  lifecycle { prevent_destroy = true }
}
resource "aws_secretsmanager_secret" "vapid" {
  name                    = "hw/prod/vapid-private-key"
  recovery_window_in_days = 30
  lifecycle { prevent_destroy = true }
}
# Values are populated out of band; no secret versions or passwords in Terraform.
resource "random_password" "origin_verify" {
  length  = 40
  special = false
}
module "compute" {
  source                 = "../../modules/compute"
  name                   = local.name
  vpc_id                 = module.network.vpc_id
  public_subnet_ids      = module.network.public_subnet_ids
  app_subnet_ids         = module.network.app_subnet_ids
  sg_alb_id              = module.network.sg_ids.alb
  sg_app_id              = module.network.sg_ids.app
  sg_api_id              = module.network.sg_ids.api
  image                  = local.image
  worker_image           = local.image
  jobs_image             = local.image
  receipts_bucket_arn    = module.storage.bucket_arn
  worker_queue_arn       = module.queue.queue_arn
  desired_count          = 2
  autoscaling_enabled    = true
  autoscaling_min        = 2
  autoscaling_max        = 4
  log_retention_days     = 30
  job_schedules_enabled  = false
  origin_certificate_arn = var.origin_certificate_arn
  origin_verify_header   = random_password.origin_verify.result
  ses_from_address       = var.ses_sender
  secret_arns            = [aws_secretsmanager_secret.runtime.arn, aws_secretsmanager_secret.gemini.arn, aws_secretsmanager_secret.vapid.arn, module.cache.auth_token_secret_arn]
  api_environment = merge(local.db_environment, {
    COGNITO_ISSUER     = module.cognito.issuer
    COGNITO_JWKS_URI   = module.cognito.jwks_uri
    COGNITO_CLIENT_IDS = module.cognito.spa_client_id
    COGNITO_HOSTED_UI  = module.cognito.hosted_ui_base
    GEMINI_MODEL       = var.gemini_model, S3_BUCKET = module.storage.bucket_name
    REDIS_HOST         = module.cache.endpoint_address, REDIS_PORT = tostring(module.cache.port)
    REDIS_SSL_CA       = "/etc/ssl/certs/ca-certificates.crt"
  })
  api_secrets = merge(local.db_secrets, {
    GEMINI_API_KEY    = aws_secretsmanager_secret.gemini.arn
    VAPID_PRIVATE_KEY = aws_secretsmanager_secret.vapid.arn
    REDIS_AUTH_TOKEN  = module.cache.auth_token_secret_arn
  })
  worker_environment = merge(local.db_environment, {
    S3_BUCKET    = module.storage.bucket_name, SQS_QUEUE_URL = module.queue.queue_url
    GEMINI_MODEL = var.gemini_model, TEXTRACT_FALLBACK_ENABLED = "true", TEXTRACT_REGION = "ap-southeast-1"
  })
  worker_secrets   = merge(local.db_secrets, { GEMINI_API_KEY = aws_secretsmanager_secret.gemini.arn })
  jobs_environment = merge(local.db_environment, { TZ = "Asia/Ho_Chi_Minh", SES_FROM_ADDRESS = var.ses_sender })
  jobs_secrets     = merge(local.db_secrets, { VAPID_PRIVATE_KEY = aws_secretsmanager_secret.vapid.arn })
}
module "migrate" {
  source                         = "../../modules/migrate"
  name                           = local.name
  cluster_name                   = module.compute.cluster_name
  image                          = local.image
  db_host                        = module.data.address
  db_secret_arn                  = module.data.secret_arn
  enable_separate_execution_role = true
  enable_runtime_bootstrap       = true
  runtime_db_secret_arn          = aws_secretsmanager_secret.runtime.arn
  log_retention_days             = 30
}
module "storage" {
  source        = "../../modules/storage"
  env           = "prod"
  force_destroy = false
  cors_origins  = [module.edge.url]
}
module "queue" {
  source      = "../../modules/queue"
  name_prefix = "homewallet-prod-"
  bucket_id   = module.storage.bucket_name
  bucket_arn  = module.storage.bucket_arn
}
module "cognito" {
  source              = "../../modules/cognito"
  name                = local.name
  callback_urls       = ["${module.edge.url}/auth/callback"]
  logout_urls         = ["${module.edge.url}/"]
  enable_dev_client   = false
  deletion_protection = "ACTIVE"
  auth_email_sender   = var.ses_sender
  log_retention_days  = 30
}
module "frontend" {
  source = "../../modules/frontend"
  env    = "prod"
}
resource "aws_route53_record" "origin" {
  zone_id = var.origin_zone_id
  name    = var.origin_hostname
  type    = "CNAME"
  ttl     = 60
  records = [module.compute.alb_dns_name]
}
module "edge" {
  source                 = "../../modules/edge"
  name                   = local.name
  frontend_bucket_id     = module.frontend.bucket_id
  frontend_bucket_arn    = module.frontend.bucket_arn
  frontend_bucket_domain = module.frontend.bucket_regional_domain_name
  alb_domain_name        = var.origin_hostname
  origin_https           = true
  origin_verify_header   = random_password.origin_verify.result
  web_acl_arn            = aws_wafv2_web_acl.frontend.arn
  depends_on             = [aws_route53_record.origin]
}

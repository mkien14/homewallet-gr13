terraform {
  required_version = ">= 1.10" # use_lockfile cần Terraform >= 1.10

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }

    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "s3" {
    bucket       = "hw-tfstate-homewallet-gr13"
    key          = "dev/terraform.tfstate"
    region       = "ap-southeast-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = "ap-southeast-1"

  default_tags {
    tags = {
      project = "homewallet"
      env     = "dev"
    }
  }
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      project = "homewallet"
      env     = "dev"
    }
  }
}

resource "random_password" "origin_verify" {
  length  = 40
  special = false
}

module "network" {
  source = "../../modules/network"

  name                         = "homewallet-dev"
  cidr                         = "10.0.0.0/16"
  azs                          = ["ap-southeast-1a", "ap-southeast-1b"]
  allow_cloudfront_http_origin = !var.close_legacy_http_origin
  nat_gateway_per_az           = var.resilience_hardening_enabled
}

module "ecr" {
  source                 = "../../modules/ecr"
  name                   = "homewallet-backend"
  preserve_tagged_images = var.application_hardening_enabled
}

module "cache" {
  source = "../../modules/cache"

  name                       = "homewallet-dev"
  subnet_ids                 = module.network.data_subnet_ids
  security_group_id          = module.network.sg_ids.cache
  num_cache_clusters         = var.resilience_hardening_enabled ? 2 : 1
  automatic_failover_enabled = var.resilience_hardening_enabled
  multi_az_enabled           = var.resilience_hardening_enabled
  snapshot_retention_limit   = var.resilience_hardening_enabled ? 7 : 0
  preferred_azs              = var.resilience_hardening_enabled ? ["ap-southeast-1a", "ap-southeast-1b"] : null
  apply_immediately          = var.resilience_hardening_enabled ? var.resilience_apply_immediately : true
}

locals {
  image = var.application_hardening_enabled ? "${module.ecr.repository_url}@${var.release_image_digest}" : coalesce(var.api_image_uri, "${module.ecr.repository_url}:${var.api_image_tag}")

  runtime_db_secret_arn = (
    var.enable_db_runtime_setup
    ? aws_secretsmanager_secret.db_runtime[0].arn
    : null
  )
  service_db_secret_arn = (
    var.use_db_runtime_credentials
    ? local.runtime_db_secret_arn
    : module.data.secret_arn
  )
}

module "compute" {
  source = "../../modules/compute"

  name                = "homewallet-dev"
  vpc_id              = module.network.vpc_id
  public_subnet_ids   = module.network.public_subnet_ids
  app_subnet_ids      = module.network.app_subnet_ids
  sg_alb_id           = module.network.sg_ids.alb
  sg_app_id           = module.network.sg_ids.app
  sg_api_id           = module.network.sg_ids.api
  image               = local.image
  receipts_bucket_arn = module.storage.bucket_arn

  desired_count                 = var.api_desired_count
  job_schedules_enabled         = var.job_schedules_enabled
  container_hardening_enabled   = var.application_hardening_enabled
  autoscaling_enabled           = var.resilience_hardening_enabled
  log_retention_days            = var.resilience_hardening_enabled ? 30 : 14
  service_discovery_arn         = var.enable_api_service_discovery ? aws_service_discovery_service.api[0].arn : null
  service_discovery_enabled     = var.enable_api_service_discovery
  readiness_healthcheck_enabled = var.enable_api_service_discovery || var.resilience_hardening_enabled

  jobs_image = var.application_hardening_enabled ? local.image : coalesce(var.jobs_image_uri, "${module.ecr.repository_url}:${var.jobs_image_tag}")

  ses_from_address = var.weekly_report_sender

  origin_verify_header = random_password.origin_verify.result

  # Keep admin DB-secret access during phase 1; remove it from the shared
  # service execution role only after hw_runtime has been bootstrapped.
  secret_arns = concat(
    var.use_db_runtime_credentials ? [] : [module.data.secret_arn],
    [
      data.aws_secretsmanager_secret.vapid_private_key.arn,
      module.cache.auth_token_secret_arn,
    ],
    var.use_db_runtime_credentials ? [local.runtime_db_secret_arn] : [],
    var.application_hardening_enabled && !var.production_ocr_enabled ? [] : [aws_secretsmanager_secret.gemini.arn],
    var.application_hardening_enabled || var.application_origin_verification_enabled ? [aws_secretsmanager_secret.origin_verification[0].arn] : []
  )

  worker_image     = var.application_hardening_enabled ? local.image : coalesce(var.worker_image_uri, "${module.ecr.repository_url}:${var.worker_image_tag}")
  worker_queue_arn = var.application_hardening_enabled ? module.queue.production_queue_arn : module.queue.queue_arn

  worker_environment = merge({
    DB_HOST   = module.data.address
    DB_PORT   = "3306"
    DB_NAME   = "homewallet"
    DB_SSL_CA = "/etc/ssl/rds-global-bundle.pem"

    S3_BUCKET                 = module.storage.bucket_name
    SQS_QUEUE_URL             = var.application_hardening_enabled ? module.queue.production_queue_url : module.queue.queue_url
    AWS_REGION                = "ap-southeast-1"
    GEMINI_MODEL              = var.gemini_model
    TEXTRACT_FALLBACK_ENABLED = var.application_hardening_enabled ? "false" : "true"
    TEXTRACT_REGION           = "ap-southeast-1"
    }, local.hardened_environment, var.application_hardening_enabled ? {
    GEMINI_ENABLED            = tostring(var.production_ocr_enabled)
    GEMINI_ROTATION_CONFIRMED = tostring(var.gemini_rotation_confirmed)
  } : {})

  worker_secrets = merge({
    DB_USER     = "${local.service_db_secret_arn}:username::"
    DB_PASSWORD = "${local.service_db_secret_arn}:password::"
  }, var.application_hardening_enabled && !var.production_ocr_enabled ? {} : { GEMINI_API_KEY = aws_secretsmanager_secret.gemini.arn })

  jobs_environment = merge({
    DB_HOST          = module.data.address
    DB_PORT          = "3306"
    DB_NAME          = "homewallet"
    DB_SSL_CA        = "/etc/ssl/rds-global-bundle.pem"
    AWS_REGION       = "ap-southeast-1"
    TZ               = "Asia/Ho_Chi_Minh"
    SES_FROM_ADDRESS = var.weekly_report_sender
  }, local.hardened_environment, var.application_hardening_enabled ? { OCR_ENABLED = "false" } : {})

  jobs_secrets = {
    DB_USER           = "${local.service_db_secret_arn}:username::"
    DB_PASSWORD       = "${local.service_db_secret_arn}:password::"
    VAPID_PRIVATE_KEY = data.aws_secretsmanager_secret.vapid_private_key.arn
  }

  api_environment = merge({
    COGNITO_ISSUER     = module.cognito.issuer
    COGNITO_JWKS_URI   = module.cognito.jwks_uri
    COGNITO_CLIENT_IDS = join(",", compact([module.cognito.spa_client_id, var.application_hardening_enabled ? null : module.cognito.dev_client_id]))
    COGNITO_HOSTED_UI  = module.cognito.hosted_ui_base
    DB_HOST            = module.data.address
    DB_PORT            = "3306"
    DB_NAME            = "homewallet"
    DB_SSL_CA          = "/etc/ssl/rds-global-bundle.pem"
    GEMINI_MODEL       = var.gemini_model
    S3_BUCKET          = module.storage.bucket_name
    AWS_REGION         = "ap-southeast-1"
    REDIS_HOST         = module.cache.endpoint_address
    REDIS_PORT         = tostring(module.cache.port)
    REDIS_SSL_CA       = "/etc/ssl/certs/ca-certificates.crt"
  }, local.hardened_environment)

  api_secrets = merge({
    DB_USER           = "${local.service_db_secret_arn}:username::"
    DB_PASSWORD       = "${local.service_db_secret_arn}:password::"
    REDIS_AUTH_TOKEN  = module.cache.auth_token_secret_arn
    VAPID_PRIVATE_KEY = data.aws_secretsmanager_secret.vapid_private_key.arn
    }, var.application_hardening_enabled ? {
    ORIGIN_VERIFY_HEADER       = aws_secretsmanager_secret.origin_verification[0].arn
    } : merge({ GEMINI_API_KEY = aws_secretsmanager_secret.gemini.arn }, var.application_origin_verification_enabled ? {
      ORIGIN_VERIFY_HEADER     = aws_secretsmanager_secret.origin_verification[0].arn
  } : {}))
}

module "data" {
  source = "../../modules/data"

  name                       = "homewallet-dev"
  data_subnet_ids            = module.network.data_subnet_ids
  sg_db_id                   = module.network.sg_ids.db
  instance_class             = "db.t4g.micro"
  multi_az                   = var.resilience_hardening_enabled
  backup_retention           = var.resilience_hardening_enabled ? 14 : 7
  deletion_protection        = var.resilience_hardening_enabled
  skip_final_snapshot        = !var.resilience_hardening_enabled
  delete_automated_backups   = !var.resilience_hardening_enabled
  copy_tags_to_snapshot      = var.resilience_hardening_enabled
  auto_minor_version_upgrade = !var.resilience_hardening_enabled
  backup_window              = var.resilience_hardening_enabled ? "18:00-19:00" : null
  maintenance_window         = var.resilience_hardening_enabled ? "sun:20:00-sun:21:00" : null
  apply_immediately          = var.resilience_hardening_enabled ? var.resilience_apply_immediately : true
}

module "migrate" {
  source = "../../modules/migrate"

  name               = "homewallet-dev"
  cluster_name       = module.compute.cluster_name
  image              = coalesce(var.migrate_image_uri, "${module.ecr.repository_url}:${var.migrate_image_tag}")
  db_host            = module.data.address
  db_secret_arn      = module.data.secret_arn
  log_retention_days = var.resilience_hardening_enabled ? 30 : 14

  enable_separate_execution_role = var.enable_db_runtime_setup
  legacy_execution_role_arn      = module.compute.execution_role_arn

  enable_runtime_bootstrap = var.enable_db_runtime_setup

  runtime_db_secret_arn = local.runtime_db_secret_arn
}

module "cognito" {
  self_signup_enabled = !var.application_hardening_enabled || var.production_public_registration
  log_retention_days  = var.resilience_hardening_enabled ? 30 : 14
  source              = "../../modules/cognito"

  name = "homewallet-dev"
  callback_urls = concat(var.application_hardening_enabled ? [] : ["http://localhost:5173/auth/callback"], [
    "${module.edge.url}/auth/callback"
  ])

  logout_urls = concat(var.application_hardening_enabled ? [] : ["http://localhost:5173/"], [
    "${module.edge.url}/"
  ])

  auth_email_sender   = var.weekly_report_sender
  enable_dev_client   = !var.application_hardening_enabled
  deletion_protection = var.application_hardening_enabled ? "ACTIVE" : "INACTIVE"


}
module "storage" {
  source = "../../modules/storage"

  env = "dev"
  cors_origins = [
    "http://localhost:5173",
    module.edge.url
  ]

  force_destroy = true
}
module "queue" {
  source = "../../modules/queue"

  bucket_id              = module.storage.bucket_name
  bucket_arn             = module.storage.bucket_arn
  production_ocr_enabled = var.application_hardening_enabled
}

resource "aws_secretsmanager_secret" "gemini" {
  name = "hw/dev/gemini-api-key"

  lifecycle {
    prevent_destroy = true
  }
}

data "aws_secretsmanager_secret" "vapid_private_key" {
  name = "hw/dev/vapid-private-key"
}

module "team_access" {
  source = "../../modules/team-access"

  name                       = "homewallet-dev"
  state_bucket               = "hw-tfstate-homewallet-gr13"
  receipts_bucket_arn        = module.storage.bucket_arn
  user_pool_arn              = module.cognito.user_pool_arn
  integration_test_user_name = "hoang"
}

module "frontend" {
  source = "../../modules/frontend"

  env = "dev"
}

module "edge" {
  source = "../../modules/edge"

  name = "homewallet-dev"

  frontend_bucket_id     = module.frontend.bucket_id
  frontend_bucket_arn    = module.frontend.bucket_arn
  frontend_bucket_domain = module.frontend.bucket_regional_domain_name

  alb_domain_name         = module.compute.alb_dns_name
  origin_verify_header    = random_password.origin_verify.result
  web_acl_arn             = aws_wafv2_web_acl.frontend.arn
  api_origin_domain_name  = var.route_api_via_https_gateway ? module.api_https[0].origin_domain_name : null
  api_origin_https        = var.route_api_via_https_gateway
  content_security_policy = var.application_hardening_enabled ? local.application_csp : var.content_security_policy
}

module "api_https" {
  count  = var.enable_api_https_gateway ? 1 : 0
  source = "../../modules/api-https"

  name                      = "homewallet-dev"
  vpc_id                    = module.network.vpc_id
  subnet_ids                = module.network.app_subnet_ids
  alb_security_group_id     = module.network.sg_ids.alb
  alb_listener_arn          = module.compute.alb_listener_arn
  api_security_group_id     = module.network.sg_ids.app
  service_discovery_arn     = var.enable_api_service_discovery ? aws_service_discovery_service.api[0].arn : null
  service_discovery_enabled = var.enable_api_service_discovery
}

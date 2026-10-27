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

resource "random_password" "origin_verify" {
  length  = 40
  special = false
}

module "network" {
  source = "../../modules/network"

  name = "homewallet-dev"
  cidr = "10.0.0.0/16"
  azs  = ["ap-southeast-1a", "ap-southeast-1b"]
}

module "ecr" {
  source = "../../modules/ecr"
  name   = "homewallet-backend"
}

locals {
  image = "${module.ecr.repository_url}:v0.4"
}

module "compute" {
  source = "../../modules/compute"

  name                = "homewallet-dev"
  vpc_id              = module.network.vpc_id
  public_subnet_ids   = module.network.public_subnet_ids
  app_subnet_ids      = module.network.app_subnet_ids
  sg_alb_id           = module.network.sg_ids.alb
  sg_app_id           = module.network.sg_ids.app
  image               = local.image
  receipts_bucket_arn = module.storage.bucket_arn

  origin_verify_header = random_password.origin_verify.result

  secret_arns = [
    module.data.secret_arn,
    aws_secretsmanager_secret.gemini.arn
  ]

  worker_image     = "${module.ecr.repository_url}:${var.worker_image_tag}"
  worker_queue_arn = module.queue.queue_arn

  worker_environment = {
    DB_HOST   = module.data.address
    DB_PORT   = "3306"
    DB_NAME   = "homewallet"
    DB_SSL_CA = "/etc/ssl/rds-global-bundle.pem"

    S3_BUCKET     = module.storage.bucket_name
    SQS_QUEUE_URL = module.queue.queue_url
    AWS_REGION    = "ap-southeast-1"
    GEMINI_MODEL  = var.gemini_model
  }

  worker_secrets = {
    DB_USER        = "${module.data.secret_arn}:username::"
    DB_PASSWORD    = "${module.data.secret_arn}:password::"
    GEMINI_API_KEY = aws_secretsmanager_secret.gemini.arn
  }

  api_environment = {
    COGNITO_ISSUER     = module.cognito.issuer
    COGNITO_JWKS_URI   = module.cognito.jwks_uri
    COGNITO_CLIENT_IDS = join(",", compact([module.cognito.spa_client_id, module.cognito.dev_client_id]))
    COGNITO_HOSTED_UI  = module.cognito.hosted_ui_base
    DB_HOST            = module.data.address
    DB_PORT            = "3306"
    DB_NAME            = "homewallet"
    DB_SSL_CA          = "/etc/ssl/rds-global-bundle.pem"
    GEMINI_MODEL       = var.gemini_model
    S3_BUCKET          = module.storage.bucket_name
    AWS_REGION         = "ap-southeast-1"
  }

  api_secrets = {
    DB_USER        = "${module.data.secret_arn}:username::"
    DB_PASSWORD    = "${module.data.secret_arn}:password::"
    GEMINI_API_KEY = aws_secretsmanager_secret.gemini.arn
  }
}

module "data" {
  source = "../../modules/data"

  name                = "homewallet-dev"
  data_subnet_ids     = module.network.data_subnet_ids
  sg_db_id            = module.network.sg_ids.db
  instance_class      = "db.t4g.micro"
  deletion_protection = false
  skip_final_snapshot = true
}

module "migrate" {
  source = "../../modules/migrate"

  name               = "homewallet-dev"
  cluster_name       = module.compute.cluster_name
  image              = local.image
  execution_role_arn = module.compute.execution_role_arn
  db_host            = module.data.address
  db_secret_arn      = module.data.secret_arn
}

module "cognito" {
  source = "../../modules/cognito"

  name = "homewallet-dev"
  callback_urls = [
    "http://localhost:5173/auth/callback",
    "${module.edge.url}/auth/callback"
  ]

  logout_urls = [
    "http://localhost:5173/",
    "${module.edge.url}/"
  ]

  enable_dev_client   = true
  deletion_protection = "INACTIVE"


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

  bucket_id  = module.storage.bucket_name
  bucket_arn = module.storage.bucket_arn
}

resource "aws_secretsmanager_secret" "gemini" {
  name = "hw/dev/gemini-api-key"

  lifecycle {
    prevent_destroy = true
  }
}

module "team_access" {
  source = "../../modules/team-access"

  name                = "homewallet-dev"
  state_bucket        = "hw-tfstate-homewallet-gr13"
  receipts_bucket_arn = module.storage.bucket_arn
  user_pool_arn       = module.cognito.user_pool_arn
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

  alb_domain_name      = module.compute.alb_dns_name
  origin_verify_header = random_password.origin_verify.result
}

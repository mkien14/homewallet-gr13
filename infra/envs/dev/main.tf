terraform {
  required_version = ">= 1.10" # use_lockfile cần Terraform >= 1.10

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
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
  image = "${module.ecr.repository_url}:v0.3"
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


  secret_arns = [module.data.secret_arn]

  api_environment = {
    COGNITO_ISSUER     = module.cognito.issuer
    COGNITO_JWKS_URI   = module.cognito.jwks_uri
    COGNITO_CLIENT_IDS = join(",", compact([module.cognito.spa_client_id, module.cognito.dev_client_id]))
    COGNITO_HOSTED_UI  = module.cognito.hosted_ui_base
    DB_HOST            = module.data.address
    DB_PORT            = "3306"
    DB_NAME            = "homewallet"
    DB_SSL_CA          = "/etc/ssl/rds-global-bundle.pem"
    S3_BUCKET          = module.storage.bucket_name
    AWS_REGION         = "ap-southeast-1"
  }

  api_secrets = {
    DB_USER     = "${module.data.secret_arn}:username::"
    DB_PASSWORD = "${module.data.secret_arn}:password::"
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

  name                = "homewallet-dev"
  callback_urls       = ["http://localhost:5173/auth/callback"]
  logout_urls         = ["http://localhost:5173/"]
  enable_dev_client   = true
  deletion_protection = "INACTIVE"
}
module "storage" {
  source = "../../modules/storage"

  env           = "dev"
  cors_origins  = ["http://localhost:5173"]
  force_destroy = true
}
module "team_access" {
  source = "../../modules/team-access"

  name                = "homewallet-dev"
  state_bucket        = "hw-tfstate-homewallet-gr13"
  receipts_bucket_arn = module.storage.bucket_arn
  user_pool_arn       = module.cognito.user_pool_arn
}
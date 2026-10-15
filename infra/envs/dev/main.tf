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

module "compute" {
  source = "../../modules/compute"

  name              = "homewallet-dev"
  vpc_id            = module.network.vpc_id
  public_subnet_ids = module.network.public_subnet_ids
  app_subnet_ids    = module.network.app_subnet_ids
  sg_alb_id         = module.network.sg_ids.alb
  sg_app_id         = module.network.sg_ids.app
  image             = "${module.ecr.repository_url}:v0.1"
}
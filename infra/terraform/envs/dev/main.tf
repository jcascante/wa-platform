terraform {
  required_version = ">= 1.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state is required here, not optional: the deploy workflow runs on ephemeral GitHub
  # Actions runners, so state can't live on a runner's local disk between runs. Bucket/table
  # come from infra/terraform/bootstrap/ (applied once, manually — see its README section).
  # Partial config: values supplied via `-backend-config=backend.hcl` (see backend.hcl.example).
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}

locals {
  name = "wa-platform-${var.environment}"
}

module "network" {
  source = "../../modules/network"
  name   = local.name
}

module "secrets" {
  source = "../../modules/secrets"
  name   = local.name
}

module "queue" {
  source = "../../modules/queue"
  name   = local.name
}

module "database" {
  source               = "../../modules/database"
  name                 = local.name
  environment          = var.environment
  private_subnet_ids   = module.network.private_subnet_ids
  db_security_group_id = module.network.db_security_group_id
}

module "lambda_api" {
  source                  = "../../modules/lambda_api"
  name                    = local.name
  environment             = var.environment
  package_path            = var.package_path
  subnet_ids              = module.network.public_subnet_ids
  security_group_id       = module.network.lambda_security_group_id
  kms_key_id              = module.secrets.kms_key_id
  kms_key_arn             = module.secrets.kms_key_arn
  database_url_secret_arn = module.database.database_url_secret_arn
  meta_app_secret_arn     = module.secrets.meta_app_secret_arn
  queue_url               = module.queue.queue_url
  queue_arn               = module.queue.queue_arn
  aws_region              = var.aws_region
}

module "lambda_worker" {
  source                  = "../../modules/lambda_worker"
  name                    = local.name
  environment             = var.environment
  package_path            = var.package_path
  subnet_ids              = module.network.public_subnet_ids
  security_group_id       = module.network.lambda_security_group_id
  kms_key_id              = module.secrets.kms_key_id
  kms_key_arn             = module.secrets.kms_key_arn
  database_url_secret_arn = module.database.database_url_secret_arn
  meta_app_secret_arn     = module.secrets.meta_app_secret_arn
  queue_url               = module.queue.queue_url
  queue_arn               = module.queue.queue_arn
  aws_region              = var.aws_region
}

module "lambda_migrate" {
  source                  = "../../modules/lambda_migrate"
  name                    = local.name
  environment             = var.environment
  package_path            = var.package_path
  subnet_ids              = module.network.public_subnet_ids
  security_group_id       = module.network.lambda_security_group_id
  kms_key_id              = module.secrets.kms_key_id
  database_url_secret_arn = module.database.database_url_secret_arn
  meta_app_secret_arn     = module.secrets.meta_app_secret_arn
  queue_url               = module.queue.queue_url
  aws_region              = var.aws_region
}

module "bastion" {
  source               = "../../modules/bastion"
  name                 = local.name
  vpc_id               = module.network.vpc_id
  subnet_id            = module.network.public_subnet_ids[0]
  db_security_group_id = module.network.db_security_group_id
}

module "github_oidc" {
  source      = "../../modules/github_oidc"
  name        = local.name
  github_repo = var.github_repo
}

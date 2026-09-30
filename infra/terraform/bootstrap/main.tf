# Creates the S3 bucket that envs/*/main.tf's S3 backend points at. Locking uses S3's native
# conditional-write lockfile (Terraform >= 1.10), not DynamoDB — HashiCorp's now-recommended
# approach, no separate lock table to pay for or manage.
# Run once, manually, by a human with real AWS credentials — a backend's own storage can't be
# managed by Terraform configured to use that backend (chicken-and-egg), so this stays on
# local state permanently and is never touched again after the first apply. See
# infra/terraform/README.md for the full bootstrap sequence (this is step 1 of 3).

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      app_name = "wa-platform"
      env      = "shared" # state bucket backs every env, not just one
    }
  }
}

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

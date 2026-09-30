variable "environment" {
  type    = string
  default = "dev"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "package_path" {
  type        = string
  description = "Path to the Lambda deployment zip built by `make package` (see infra/terraform/README.md)"
  default     = "../../../../service/dist/wa-platform.zip"
}

variable "github_repo" {
  type        = string
  description = "owner/repo for the GitHub OIDC deploy role trust policy, e.g. \"acme/wa-platform\""
}

variable "name" {
  type = string
}

variable "environment" {
  type = string
}

variable "package_path" {
  type        = string
  description = "Path to the built deployment zip (see infra/terraform/README.md)"
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "kms_key_id" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "database_url_secret_arn" {
  type = string
}

variable "meta_app_secret_arn" {
  type = string
}

variable "queue_url" {
  type = string
}

variable "queue_arn" {
  type = string
}

variable "reserved_concurrent_executions" {
  type    = number
  default = 10
}

variable "log_retention_days" {
  type    = number
  default = 30
}

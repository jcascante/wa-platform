variable "name" {
  type = string
}

variable "environment" {
  type = string
}

variable "package_path" {
  type = string
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
  type = number
  # Matched to a fraction of db.t4g.micro's connection budget, shared with lambda_api — the
  # worker also opens KMS/tenant-webhook calls per invocation, so it gets a smaller slice.
  default = 5
}

variable "log_retention_days" {
  type    = number
  default = 30
}

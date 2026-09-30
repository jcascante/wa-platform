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

# Not actually used for KMS calls (migrations don't touch encrypted columns) — kept so the
# same Settings object used everywhere else can construct without a dummy value.
variable "kms_key_id" {
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

variable "log_retention_days" {
  type    = number
  default = 30
}

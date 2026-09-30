variable "name" {
  type = string
}

variable "github_repo" {
  type        = string
  description = "owner/repo, e.g. \"acme/wa-platform\""
}

variable "github_environment" {
  type    = string
  default = "production"
}

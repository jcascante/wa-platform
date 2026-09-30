variable "name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "db_security_group_id" {
  type = string
}

variable "instance_type" {
  type    = string
  default = "t4g.nano"
}

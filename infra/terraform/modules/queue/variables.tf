variable "name" {
  type = string
}

variable "alert_email" {
  type        = string
  default     = null
  description = "If set, subscribed to an alarm that fires when a message lands in the DLQ."
}

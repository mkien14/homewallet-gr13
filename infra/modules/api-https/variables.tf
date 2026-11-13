variable "name" { type = string }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "alb_security_group_id" { type = string }
variable "alb_listener_arn" { type = string }
variable "throttling_rate_limit" {
  type    = number
  default = 20
  validation {
    condition     = var.throttling_rate_limit > 0 && var.throttling_rate_limit <= 100
    error_message = "Choose a reviewed API rate between 1 and 100 requests/second."
  }
}

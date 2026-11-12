variable "name" {
  type = string
}
variable "origin_https" {
  type    = bool
  default = false
}

variable "frontend_bucket_id" {
  type = string
}

variable "frontend_bucket_arn" {
  type = string
}

variable "frontend_bucket_domain" {
  type = string
}

variable "alb_domain_name" {
  type = string
}

variable "origin_verify_header" {
  type      = string
  sensitive = true
}
variable "web_acl_arn" {
  description = "CloudFront WAFv2 Web ACL ARN"
  type        = string
  default     = null
}

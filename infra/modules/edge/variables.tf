variable "name" {
  type = string
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
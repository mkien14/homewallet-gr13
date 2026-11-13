variable "name" { type = string }
variable "log_retention_days" {
  type    = number
  default = 14
}
variable "origin_certificate_arn" {
  type    = string
  default = null
}
variable "autoscaling_enabled" {
  type    = bool
  default = false
}
variable "service_discovery_arn" {
  type    = string
  default = null
}
variable "service_discovery_enabled" {
  type    = bool
  default = false
}
variable "readiness_healthcheck_enabled" {
  type    = bool
  default = false
}
variable "container_hardening_enabled" {
  description = "Run reviewed production images as UID/GID 10001, drop Linux capabilities, and reap child processes."
  type        = bool
  default     = false
}
variable "autoscaling_min" {
  type    = number
  default = 2
}
variable "autoscaling_max" {
  type    = number
  default = 4
}
variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "app_subnet_ids" { type = list(string) }
variable "sg_alb_id" { type = string }
variable "sg_app_id" { type = string }
variable "sg_api_id" { type = string }
variable "image" { type = string }
variable "receipts_bucket_arn" { type = string }

variable "container_port" {
  type    = number
  default = 5000
}
variable "desired_count" {
  type    = number
  default = 2
}
variable "cpu" {
  type    = number
  default = 512
}
variable "memory" {
  type    = number
  default = 1024
}
variable "api_environment" {
  type    = map(string)
  default = {}
}

variable "api_secrets" {
  type    = map(string)
  default = {}
}

variable "secret_arns" {
  type    = list(string)
  default = []
}

variable "worker_image" {
  description = "Container image for receipt worker"
  type        = string
}

variable "worker_queue_arn" {
  description = "SQS queue consumed by worker"
  type        = string
}

variable "worker_environment" {
  type    = map(string)
  default = {}
}

variable "worker_secrets" {
  type    = map(string)
  default = {}
}

variable "jobs_image" {
  description = "Mutable dev image tag promoted only after the API deployment succeeds"
  type        = string
}

variable "jobs_environment" {
  type    = map(string)
  default = {}
}

variable "jobs_secrets" {
  type    = map(string)
  default = {}
}

variable "ses_from_address" {
  description = "Verified SES From address allowed for scheduled job emails"
  type        = string
}

variable "origin_verify_header" {
  type      = string
  sensitive = true
}
variable "job_schedules_enabled" {
  type    = bool
  default = true
}

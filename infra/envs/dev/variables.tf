variable "worker_image_tag" {
  description = "ECR image tag containing the receipt worker; Deploy Dev promotes the current backend image to dev"
  type        = string
  default     = "dev"
}

variable "gemini_model" {
  description = "Gemini model verified by the backend team"
  type        = string
}

variable "api_image_tag" {
  description = "Image tag for the Terraform-managed API task definition"
  type        = string
  default     = "v0.4"
}

variable "weekly_report_sender" {
  description = "Verified SES sender identity for recurring alerts and weekly reports"
  type        = string
  default     = "homewallet26@gmail.com"
}
variable "api_desired_count" {
  type    = number
  default = 1
}

variable "job_schedules_enabled" {
  type    = bool
  default = false
}

variable "migrate_image_tag" {
  type    = string
  default = "sha-9cee53ea92d31532b49d5fa26c6f20610418964d"
}
variable "enable_db_runtime_setup" {
  description = "Deploy the separately reviewed DB runtime setup"
  type        = bool
  default     = true
}

variable "use_db_runtime_credentials" {
  description = "Use the hw_runtime secret for API, worker, and scheduled jobs after bootstrap succeeds"
  type        = bool
  default     = true

  validation {
    condition     = !var.use_db_runtime_credentials || var.enable_db_runtime_setup
    error_message = "use_db_runtime_credentials requires enable_db_runtime_setup=true so the runtime secret and separate migration role exist."
  }
}

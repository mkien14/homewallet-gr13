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

# Preserve already-deployed digest images during the staged HTTPS transition.
# The production profile still exclusively uses release_image_digest.
variable "api_image_uri" {
  type    = string
  default = null
}
variable "worker_image_uri" {
  type    = string
  default = null
}
variable "jobs_image_uri" {
  type    = string
  default = null
}
variable "migrate_image_uri" {
  type    = string
  default = null
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

variable "enable_api_https_gateway" {
  description = "Provision HTTPS AWS origin and VPC Link; does not change CloudFront routing."
  type        = bool
  default     = false
}

variable "route_api_via_https_gateway" {
  description = "Switch existing CloudFront /api/* after controlled canary acceptance."
  type        = bool
  default     = false
  validation {
    condition     = !var.route_api_via_https_gateway || var.enable_api_https_gateway
    error_message = "HTTPS routing requires enable_api_https_gateway=true."
  }
}

variable "close_legacy_http_origin" {
  description = "Third phase only: remove the public CloudFront-to-ALB port 80 ingress after HTTPS cutover is healthy."
  type        = bool
  default     = false
  validation {
    condition     = !var.close_legacy_http_origin || var.route_api_via_https_gateway
    error_message = "Keep legacy ingress until HTTPS routing has been enabled and accepted."
  }
}

variable "content_security_policy" {
  type    = string
  default = null
}

variable "waf_enforce_common_rules" {
  description = "Move managed rules from COUNT to BLOCK after reviewing legitimate upload/auth traffic."
  type        = bool
  default     = false
}

variable "waf_enforce_api_rate" {
  type    = bool
  default = false
}

variable "application_hardening_enabled" {
  description = "Controlled promotion of this existing application stack; review data boundary and coordinate the separate resilience work first."
  type        = bool
  default     = false
  validation {
    condition = !var.application_hardening_enabled || (
      var.route_api_via_https_gateway && var.waf_enforce_common_rules && var.waf_enforce_api_rate &&
      can(regex("^[a-f0-9]{40}$", var.release_commit)) &&
      can(regex("^sha256:[a-f0-9]{64}$", var.release_image_digest)) && var.use_db_runtime_credentials &&
      var.production_budget_enabled
    )
    error_message = "Production promotion requires HTTPS routing, enforced WAF, runtime DB credentials, a reviewed 40-character commit, and its immutable registry digest for API/worker/jobs."
  }
}

variable "release_commit" {
  type    = string
  default = ""
}

variable "production_allowed_household_ids" {
  description = "Reviewed current household IDs for closed rollout; household 1 remains retained and excluded."
  type        = set(number)
  default     = []
  validation {
    condition = !var.application_hardening_enabled || (
      length(var.production_allowed_household_ids) > 0 &&
      alltrue([for id in var.production_allowed_household_ids : id > 1 && floor(id) == id])
    )
    error_message = "Production requires a fixed approved household ID list excluding household 1."
  }
}

variable "release_image_digest" {
  description = "ECR manifest digest from the scanned release image, never a mutable tag."
  type        = string
  default     = ""
}

variable "jobs_image_tag" {
  type    = string
  default = "dev"
}

variable "notifications_release_accepted" {
  description = "Separate operational acceptance; initial production profile leaves all schedules disabled."
  type        = bool
  default     = false
  validation {
    condition     = !var.application_hardening_enabled || !var.job_schedules_enabled || var.notifications_release_accepted
    error_message = "Accept the notification delivery and recipient controls before enabling production schedules."
  }
}

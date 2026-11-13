variable "release_commit" {
  description = "Reviewed 40-character main commit shared by backend/frontend artifacts."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.release_commit))
    error_message = "Use the exact reviewed Git commit SHA."
  }
}
variable "migration_image_digest" {
  description = "Separately applied migration/bootstrap image; keep fixed during application-only releases."
  type        = string
  validation {
    condition     = can(regex("^sha256:[0-9a-f]{64}$", var.migration_image_digest))
    error_message = "Use the reviewed migration image digest."
  }
}
variable "release_digest" {
  description = "Reviewed image digest in the dedicated homewallet-prod-backend repository."
  type        = string
  validation {
    condition     = can(regex("^sha256:[0-9a-f]{64}$", var.release_digest))
    error_message = "Use an immutable sha256 image digest."
  }
}
variable "expected_account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "Specify the reviewed production AWS account ID."
  }
}
variable "origin_hostname" {
  description = "DNS hostname exclusively for the ALB origin; certificate must cover this name."
  type        = string
  validation {
    condition     = !endswith(var.origin_hostname, ".amazonaws.com") && can(regex("^[a-z0-9.-]+$", var.origin_hostname))
    error_message = "Use your own origin DNS name, not the ALB AWS hostname."
  }
}
variable "origin_certificate_arn" {
  description = "Issued, DNS validated ACM certificate in ap-southeast-1 covering origin_hostname."
  type        = string
  validation {
    condition     = can(regex("^arn:aws:acm:ap-southeast-1:${var.expected_account_id}:certificate/", var.origin_certificate_arn))
    error_message = "The ALB certificate must be in the reviewed account and ap-southeast-1."
  }
}
variable "origin_zone_id" {
  description = "Reviewed public Route53 zone containing origin_hostname."
  type        = string
}
variable "gemini_model" { type = string }
variable "ses_sender" {
  description = "Explicitly approved SES verified production sender. Schedules remain disabled."
  type        = string
}
variable "db_instance_class" {
  description = "Required: verify MySQL engine/class/Multi AZ orderability and approve cost before setting."
  type        = string
}
variable "db_engine_version" {
  description = "Required: supported MySQL 8.4 release verified in ap-southeast-1."
  type        = string
  validation {
    condition     = startswith(var.db_engine_version, "8.4")
    error_message = "This parameter group requires MySQL 8.4."
  }
}
variable "final_snapshot_identifier" {
  description = "Unique approved final snapshot name; change before each authorized deletion/recreation."
  type        = string
  validation {
    condition     = can(regex("^homewallet-prod-final-[a-z0-9]+(-[a-z0-9]+)*$", var.final_snapshot_identifier))
    error_message = "Use homewallet-prod-final- followed by a unique change identifier."
  }
}
variable "operations_emails" {
  type = set(string)
  validation {
    condition     = length(var.operations_emails) > 0 && length(var.operations_emails) <= 10
    error_message = "Supply 1 to 10 approved operations recipients (AWS budget notification limit)."
  }
}
variable "monthly_budget_usd" {
  type = number
  validation {
    condition     = var.monthly_budget_usd > 0
    error_message = "Supply a reviewed positive monthly budget."
  }
}
variable "waf_count_mode" {
  description = "Staging observation only. Default production posture blocks; approval required to change."
  type        = bool
  default     = false
}
variable "waf_validation_reference" {
  description = "Required ticket/evidence for WAF false-positive review before production blocking."
  type        = string
  validation {
    condition     = length(trimspace(var.waf_validation_reference)) > 5
    error_message = "Record the WAF review evidence."
  }
}
variable "production_allowed_household_ids" {
  type = set(number)
  validation {
    condition = length(var.production_allowed_household_ids) > 0 && alltrue([
      for id in var.production_allowed_household_ids : id > 1 && floor(id) == id
    ])
    error_message = "Explicit approved household IDs are required; household 1 is retained and excluded."
  }
}

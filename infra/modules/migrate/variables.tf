variable "name" { type = string }
variable "cluster_name" { type = string }
variable "image" { type = string }
variable "db_host" { type = string }
variable "db_secret_arn" { type = string }
variable "enable_runtime_bootstrap" {
  description = "Create the controlled runtime DB bootstrap task"
  type        = bool
  default     = false
}

variable "runtime_db_secret_arn" {
  description = "Runtime DB secret containing username and password"
  type        = string
  default     = null
  nullable    = true
}

variable "enable_separate_execution_role" {
  type    = bool
  default = false
}

variable "legacy_execution_role_arn" {
  type     = string
  default  = null
  nullable = true
}
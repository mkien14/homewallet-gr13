variable "name" {
  type = string
}
variable "num_cache_clusters" {
  type    = number
  default = 1
}
variable "automatic_failover_enabled" {
  type    = bool
  default = false
  validation {
    condition     = !var.automatic_failover_enabled || var.num_cache_clusters >= 2
    error_message = "Automatic failover requires at least two cache nodes."
  }
}
variable "multi_az_enabled" {
  type    = bool
  default = false
  validation {
    condition     = !var.multi_az_enabled || var.automatic_failover_enabled
    error_message = "Multi AZ requires automatic failover."
  }
}
variable "snapshot_retention_limit" {
  type    = number
  default = 0
}
variable "apply_immediately" {
  type    = bool
  default = true
}
variable "auth_secret_name" {
  type    = string
  default = null
}
variable "preferred_azs" {
  type    = list(string)
  default = null
}

variable "subnet_ids" {
  description = "Private data subnets for the Redis subnet group"
  type        = list(string)
}

variable "security_group_id" {
  description = "Cache security group; ingress is restricted to the API identity SG"
  type        = string
}

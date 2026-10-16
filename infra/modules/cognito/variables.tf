variable "name" { type = string }

variable "callback_urls" { type = list(string) }
variable "logout_urls" { type = list(string) }

variable "domain_prefix" {
  type    = string
  default = null 
}

variable "user_pool_tier" {
  type    = string
  default = "ESSENTIALS"
}

variable "deletion_protection" {
  type    = string
  default = "INACTIVE" # prod: "ACTIVE"
}

variable "enable_dev_client" {
  type    = bool
  default = false
}
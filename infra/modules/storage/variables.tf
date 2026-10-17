variable "env" { type = string }

variable "cors_origins" { type = list(string) }

variable "force_destroy" {
  type    = bool
  default = false
}
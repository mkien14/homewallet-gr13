variable "name"              { type = string }
variable "vpc_id"            { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "app_subnet_ids"    { type = list(string) }
variable "sg_alb_id"         { type = string }
variable "sg_app_id"         { type = string }
variable "image"             { type = string } 
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
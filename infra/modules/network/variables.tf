variable "name" {
  type = string
}

variable "cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "azs" {
  type = list(string)
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.0.0/24", "10.0.1.0/24"]
}

variable "app_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "data_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.20.0/24", "10.0.21.0/24"]
}

variable "alb_ingress_cidr" {
  type    = string
  default = "0.0.0.0/0"
}
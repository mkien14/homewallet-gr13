variable "name" {
  type = string
}

variable "subnet_ids" {
  description = "Private data subnets for the Redis subnet group"
  type        = list(string)
}

variable "security_group_id" {
  description = "Cache security group; ingress is restricted to the API identity SG"
  type        = string
}

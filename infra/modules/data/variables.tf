variable "name"               { type = string }
variable "data_subnet_ids"    { type = list(string) }
variable "sg_db_id"           { type = string }

variable "instance_class" {
  type    = string
  default = "db.t4g.micro"
}
variable "engine_version" {
  type    = string
  default = "8.4"
}
variable "backup_retention" {
  type    = number
  default = 7
}
variable "multi_az" {
  type    = bool
  default = false
}
variable "deletion_protection" {
  type    = bool
  default = false
}
variable "skip_final_snapshot" {
  type    = bool
  default = true
}
variable "name" { type = string }
variable "apply_immediately" {
  type    = bool
  default = true
}
variable "auto_minor_version_upgrade" {
  type    = bool
  default = true
}
variable "backup_window" {
  type    = string
  default = null
}
variable "maintenance_window" {
  type    = string
  default = null
}
variable "copy_tags_to_snapshot" {
  type    = bool
  default = false
}
variable "delete_automated_backups" {
  type    = bool
  default = true
}
variable "final_snapshot_identifier" {
  description = "Change-approved unique deletion snapshot ID; never timestamp() on every plan."
  type        = string
  default     = null
}
variable "data_subnet_ids" { type = list(string) }
variable "sg_db_id" { type = string }

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

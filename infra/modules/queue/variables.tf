variable "bucket_id" {
  type = string
}
variable "name_prefix" {
  type    = string
  default = ""
}

variable "bucket_arn" {
  type = string
}

variable "production_ocr_enabled" {
  type    = bool
  default = false
}

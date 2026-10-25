data "aws_caller_identity" "current" {}

variable "env" {
  type = string
}

# Preserve the existing bucket at its original Terraform state address.
resource "aws_s3_bucket" "frontend" {
  bucket        = "hw-frontend-${var.env}-${data.aws_caller_identity.current.account_id}"
  force_destroy = false

  lifecycle {
    prevent_destroy = true
  }
}

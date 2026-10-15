provider "aws" { region = "ap-southeast-1" }

resource "aws_s3_bucket" "tfstate" {
  bucket = "hw-tfstate-homewallet-gr13"  
}
resource "aws_s3_bucket_versioning" "v" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_public_access_block" "b" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
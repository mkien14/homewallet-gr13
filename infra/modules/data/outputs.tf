output "address" { value = aws_db_instance.this.address }
output "safety_policy" {
  value = {
    multi_az            = aws_db_instance.this.multi_az
    retention           = aws_db_instance.this.backup_retention_period
    deletion_protection = aws_db_instance.this.deletion_protection
    skip_final_snapshot = aws_db_instance.this.skip_final_snapshot
    public              = aws_db_instance.this.publicly_accessible
    encrypted           = aws_db_instance.this.storage_encrypted
    immediate           = aws_db_instance.this.apply_immediately
  }
}
output "port" { value = aws_db_instance.this.port }

output "secret_arn" {
  value = aws_db_instance.this.master_user_secret[0].secret_arn
}
output "identifier" {
  value = aws_db_instance.this.identifier
}

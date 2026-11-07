resource "aws_secretsmanager_secret" "db_runtime" {
  name        = "hw/dev/db-runtime"
  description = "Limited MySQL credentials for API, worker and jobs"

  lifecycle {
    prevent_destroy = true
  }
}

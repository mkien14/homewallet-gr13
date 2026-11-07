resource "aws_secretsmanager_secret" "db_runtime" {
  count = var.enable_db_runtime_setup ? 1 : 0

  name        = "hw/dev/db-runtime"
  description = "Limited MySQL credentials for API, worker and jobs"

  lifecycle {
    prevent_destroy = true
  }
}

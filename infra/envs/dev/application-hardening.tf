# Existing-stack promotion, not a second VPC/RDS/Redis deployment. This leaves
# the availability/restore/scaling work with its assigned owner. Nothing below
# is enabled by default; no legacy household, receipt or DLQ data is deleted.
resource "aws_secretsmanager_secret" "origin_verification" {
  count                   = var.application_hardening_enabled ? 1 : 0
  name                    = "hw/production/origin-verification"
  recovery_window_in_days = 30
}

resource "aws_secretsmanager_secret_version" "origin_verification" {
  count         = var.application_hardening_enabled ? 1 : 0
  secret_id     = aws_secretsmanager_secret.origin_verification[0].id
  secret_string = random_password.origin_verify.result
}

locals {
  hardened_environment = var.application_hardening_enabled ? {
    APP_ENV                          = "production"
    APP_RELEASE                      = var.release_commit
    PRODUCTION_ALLOWED_HOUSEHOLD_IDS = join(",", sort([for id in var.production_allowed_household_ids : tostring(id)]))
    RATE_LIMIT_ENABLED               = "true"
    OCR_REQUIRE_CONSENT              = "true"
    OCR_ENABLED                      = "false"
    GEMINI_ENABLED                   = "false"
    GEMINI_ROTATION_CONFIRMED        = "false"
    GEMINI_MAX_TRIES                 = "2"
    API_REQUESTS_PER_MINUTE          = "120"
    API_WRITES_PER_MINUTE            = "30"
    RECEIPTS_PER_USER_DAY            = "10"
    RECEIPTS_PER_HOUSEHOLD_DAY       = "30"
    RECEIPTS_GLOBAL_DAY              = "200"
    AI_SUGGESTIONS_PER_USER_DAY      = "10"
    AI_SUGGESTIONS_PER_HOUSEHOLD_DAY = "20"
    AI_SUGGESTIONS_GLOBAL_DAY        = "100"
  } : {}

  receipt_origins = "https://${module.storage.bucket_name}.s3.ap-southeast-1.amazonaws.com https://${module.storage.bucket_name}.s3.amazonaws.com"
  application_csp = join("; ", [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob: ${local.receipt_origins}",
    "connect-src 'self' https://cognito-idp.ap-southeast-1.amazonaws.com ${module.cognito.hosted_ui_base} ${local.receipt_origins}",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self' ${module.cognito.hosted_ui_base}",
    "worker-src 'self'",
    "upgrade-insecure-requests",
  ])
}

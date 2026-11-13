# Additional account-wide alert approved by Kien: keep existing group budgets.
variable "production_budget_enabled" {
  type    = bool
  default = false
}
variable "production_monthly_budget_usd" {
  type    = number
  default = 100
  validation {
    condition     = var.production_monthly_budget_usd > 0
    error_message = "Monthly cost alert must be positive."
  }
}
variable "production_budget_emails" {
  type      = list(string)
  sensitive = true
  default   = []
  validation {
    condition = !var.production_budget_enabled || (
      length(var.production_budget_emails) > 0 && length(var.production_budget_emails) <= 10 &&
      alltrue([for email in var.production_budget_emails : can(regex("^[^ @]+@[^ @]+\\.[^ @]+$", email))])
    )
    error_message = "Review at least one alert recipient before enabling the budget."
  }
}
data "aws_caller_identity" "production_budget" {
  count = var.production_budget_enabled ? 1 : 0
}
resource "aws_budgets_budget" "production" {
  count        = var.production_budget_enabled ? 1 : 0
  account_id   = data.aws_caller_identity.production_budget[0].account_id
  name         = "HomeWallet-Production-Monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.production_monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = { actual_50 = ["ACTUAL", 50], actual_80 = ["ACTUAL", 80], actual_100 = ["ACTUAL", 100], forecast_100 = ["FORECASTED", 100] }
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value[1]
      threshold_type             = "PERCENTAGE"
      notification_type          = notification.value[0]
      subscriber_email_addresses = var.production_budget_emails
    }
  }
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = data.aws_caller_identity.production_budget[0].account_id == "179923444714"
      error_message = "Wrong account for the approved production alert."
    }
  }
}

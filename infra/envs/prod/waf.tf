resource "aws_wafv2_web_acl" "frontend" {
  provider = aws.us_east_1
  name     = "homewallet-prod-cloudfront"
  scope    = "CLOUDFRONT"
  default_action {
    allow {}
  }
  dynamic "rule" {
    for_each = { common = "AWSManagedRulesCommonRuleSet", bad_inputs = "AWSManagedRulesKnownBadInputsRuleSet" }
    content {
      name     = rule.key
      priority = rule.key == "common" ? 1 : 2
      override_action {
        dynamic "count" {
          for_each = var.waf_count_mode ? [1] : []
          content {}
        }
        dynamic "none" {
          for_each = var.waf_count_mode ? [] : [1]
          content {}
        }
      }
      statement {
        managed_rule_group_statement {
          name        = rule.value
          vendor_name = "AWS"
        }
      }
      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = "homewallet-prod-${rule.key}"
        sampled_requests_enabled   = false
      }
    }
  }
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "homewallet-prod-waf"
    sampled_requests_enabled   = false
  }
}

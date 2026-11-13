resource "aws_wafv2_web_acl" "frontend" {
  provider = aws.us_east_1

  name  = "homewallet-dev-cloudfront"
  scope = "CLOUDFRONT"

  default_action {
    allow {}
  }

  rule {
    name     = "common-count"
    priority = 1

    override_action {
      dynamic "count" {
        for_each = var.waf_enforce_common_rules ? [] : [1]
        content {}
      }
      dynamic "none" {
        for_each = var.waf_enforce_common_rules ? [1] : []
        content {}
      }
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "hw-dev-common-count"
      sampled_requests_enabled   = false
    }
  }

  rule {
    name     = "api-ip-rate"
    priority = 2
    action {
      dynamic "count" {
        for_each = var.waf_enforce_api_rate ? [] : [1]
        content {}
      }
      dynamic "block" {
        for_each = var.waf_enforce_api_rate ? [1] : []
        content {}
      }
    }
    statement {
      rate_based_statement {
        aggregate_key_type = "IP"
        limit              = 2000
        scope_down_statement {
          byte_match_statement {
            positional_constraint = "STARTS_WITH"
            search_string         = "/api/"
            field_to_match {
              uri_path {}
            }
            text_transformation {
              priority = 0
              type     = "NONE"
            }
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "hw-dev-api-ip-rate"
      sampled_requests_enabled   = false
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "hw-dev-waf"
    sampled_requests_enabled   = false
  }
}

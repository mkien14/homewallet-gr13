# Browser -> CloudFront -> execute-api is HTTPS. The private HTTP hop uses
# Cloud Map SRV discovery directly to ECS, or the original ALB integration.
# Application origin verification is required for direct ECS integration.
# No public default route, CORS wildcard, payload logging, or second ALB.
resource "aws_security_group" "link" {
  name        = "${var.name}-vpc-link"
  description = "API Gateway private integration identity"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_egress_rule" "link_to_alb" {
  security_group_id            = aws_security_group.link.id
  referenced_security_group_id = var.alb_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
}

resource "aws_vpc_security_group_ingress_rule" "alb_from_link" {
  security_group_id            = var.alb_security_group_id
  referenced_security_group_id = aws_security_group.link.id
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
}

resource "aws_apigatewayv2_vpc_link" "this" {
  name               = "${var.name}-private-api"
  subnet_ids         = var.subnet_ids
  security_group_ids = [aws_security_group.link.id]
}

resource "aws_apigatewayv2_api" "this" {
  name                         = "${var.name}-https-api"
  protocol_type                = "HTTP"
  disable_execute_api_endpoint = false
}

resource "aws_apigatewayv2_integration" "alb" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "ANY"
  integration_uri        = var.service_discovery_enabled ? var.service_discovery_arn : var.alb_listener_arn
  connection_type        = "VPC_LINK"
  connection_id          = aws_apigatewayv2_vpc_link.this.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 30000
  request_parameters = {
    "overwrite:path" = "$request.path"
  }
}

resource "aws_apigatewayv2_route" "api" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "ANY /api/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.alb.id}"
}

resource "aws_apigatewayv2_stage" "this" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.access.arn
    format = jsonencode({
      request_id         = "$context.requestId"
      status             = "$context.status"
      integration_status = "$context.integrationStatus"
      integration_error  = "$context.integrationErrorMessage"
      response_latency   = "$context.responseLatency"
    })
  }
  default_route_settings {
    throttling_burst_limit = 40
    throttling_rate_limit  = var.throttling_rate_limit
  }
  depends_on = [aws_apigatewayv2_route.api, aws_vpc_security_group_ingress_rule.alb_from_link]
}

resource "aws_cloudwatch_log_group" "access" {
  name              = "/aws/apigateway/${var.name}-https-api"
  retention_in_days = 30
}

resource "aws_vpc_security_group_egress_rule" "link_to_api" {
  count                        = var.service_discovery_enabled ? 1 : 0
  security_group_id            = aws_security_group.link.id
  referenced_security_group_id = var.api_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5000
  to_port                      = 5000
}

resource "aws_vpc_security_group_ingress_rule" "api_from_link" {
  count                        = var.service_discovery_enabled ? 1 : 0
  security_group_id            = var.api_security_group_id
  referenced_security_group_id = aws_security_group.link.id
  ip_protocol                  = "tcp"
  from_port                    = 5000
  to_port                      = 5000
}

output "origin_domain_name" {
  value = trimprefix(aws_apigatewayv2_api.this.api_endpoint, "https://")
}
output "vpc_link_id" { value = aws_apigatewayv2_vpc_link.this.id }
output "api_id" { value = aws_apigatewayv2_api.this.id }

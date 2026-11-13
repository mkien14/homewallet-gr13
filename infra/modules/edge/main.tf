data "aws_cloudfront_cache_policy" "frontend" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "api" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "api" {
  name = "Managed-AllViewerExceptHostHeader"
}

data "aws_cloudfront_response_headers_policy" "security" {
  name = "Managed-SecurityHeadersPolicy"
}

resource "aws_cloudfront_response_headers_policy" "application" {
  count = var.content_security_policy == null ? 0 : 1
  name  = "${var.name}-application-security"

  security_headers_config {
    content_security_policy {
      content_security_policy = var.content_security_policy
      override                = true
    }
    content_type_options { override = true }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
    strict_transport_security {
      access_control_max_age_sec = 31536000
      override                   = true
    }
  }
  custom_headers_config {
    items {
      header   = "Permissions-Policy"
      value    = "camera=(), microphone=(), geolocation=()"
      override = true
    }
  }
}

locals {
  security_headers_policy_id = var.content_security_policy == null ? data.aws_cloudfront_response_headers_policy.security.id : aws_cloudfront_response_headers_policy.application[0].id
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.name}-frontend-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_function" "spa" {
  name    = "${var.name}-spa-rewrite"
  runtime = "cloudfront-js-2.0"
  publish = true
  # Preserve the deployed CRLF format without changing the function logic.
  code = replace(replace(file("${path.module}/spa-rewrite.js"), "\r\n", "\n"), "\n", "\r\n")
}

resource "aws_cloudfront_distribution" "this" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  comment             = "${var.name} frontend and API"
  web_acl_id          = var.web_acl_arn

  origin {
    origin_id                = "frontend-s3"
    domain_name              = var.frontend_bucket_domain
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id

  }

  origin {
    origin_id   = "backend-alb"
    domain_name = coalesce(var.api_origin_domain_name, var.alb_domain_name)

    custom_header {
      name  = "X-Origin-Verify"
      value = var.origin_verify_header
    }

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = (var.origin_https || var.api_origin_https) ? "https-only" : "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "frontend-s3"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD", "OPTIONS"]
    cached_methods  = ["GET", "HEAD"]
    compress        = true

    cache_policy_id = data.aws_cloudfront_cache_policy.frontend.id

    response_headers_policy_id = (
      local.security_headers_policy_id
    )

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa.arn
    }
  }

  ordered_cache_behavior {
    path_pattern           = "/api/*"
    target_origin_id       = "backend-alb"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = [
      "GET",
      "HEAD",
      "OPTIONS",
      "PUT",
      "POST",
      "PATCH",
      "DELETE"
    ]

    cached_methods = ["GET", "HEAD"]
    compress       = true

    cache_policy_id = data.aws_cloudfront_cache_policy.api.id

    origin_request_policy_id = (
      data.aws_cloudfront_origin_request_policy.api.id
    )

    response_headers_policy_id = (
      local.security_headers_policy_id
    )
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = var.frontend_bucket_id

  # Build the same policy directly so a WAF update does not defer a data read.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowCloudFrontRead"
      Effect    = "Allow"
      Action    = "s3:GetObject"
      Resource  = "${var.frontend_bucket_arn}/*"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.this.arn
        }
      }
    }]
  })
}

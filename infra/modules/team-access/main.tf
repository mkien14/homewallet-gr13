data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  log_arn = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/ecs/hw-*:*"
}

data "aws_iam_policy_document" "dev" {
  statement {
    sid       = "StateList"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.state_bucket}"]
  }
  statement {
    sid       = "StateRead"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${var.state_bucket}/*"]
  }
  statement {
    sid       = "ReceiptsObjects"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${var.receipts_bucket_arn}/receipts/*"]
  }
  statement {
    sid       = "ReceiptsList"
    actions   = ["s3:ListBucket", "s3:GetBucketVersioning"]
    resources = [var.receipts_bucket_arn]
  }
  statement {
    sid = "CognitoTestUsers"
    actions = [
      "cognito-idp:AdminCreateUser", "cognito-idp:AdminSetUserPassword",
      "cognito-idp:AdminDeleteUser", "cognito-idp:AdminGetUser", "cognito-idp:ListUsers",
    ]
    resources = [var.user_pool_arn]
  }
  statement {
    sid       = "EcsReadOnly"
    actions   = ["ecs:Describe*", "ecs:List*"]
    resources = ["*"]
  }
  statement {
    sid       = "LogsList"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]
  }
  statement {
    sid       = "LogsRead"
    actions   = ["logs:DescribeLogStreams", "logs:GetLogEvents", "logs:FilterLogEvents"]
    resources = [local.log_arn]
  }
}

resource "aws_iam_group" "developers" {
  name = "${var.name}-developers"
}

resource "aws_iam_group_policy" "developers" {
  name   = "dev-access"
  group  = aws_iam_group.developers.name
  policy = data.aws_iam_policy_document.dev.json
}

data "aws_iam_policy_document" "integration_test_receipts" {
  statement {
    sid       = "ListTestBucketVersions"
    actions   = ["s3:ListBucketVersions"]
    resources = [var.receipts_bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["receipts/uploads/integration-test/*"]
    }
  }

  statement {
    sid       = "DeleteTestObjectVersions"
    actions   = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
    resources = ["${var.receipts_bucket_arn}/receipts/uploads/integration-test/*"]
  }
}

resource "aws_iam_user_policy" "integration_test_receipts" {
  name   = "${var.name}-receipt-integration-test"
  user   = var.integration_test_user_name
  policy = data.aws_iam_policy_document.integration_test_receipts.json
}

data "aws_iam_policy_document" "cognito_branding" {
  statement {
    sid       = "DiscoverPools"
    actions   = ["cognito-idp:ListUserPools"]
    resources = ["*"]
  }

  statement {
    sid = "ReadAndEditDevPoolBranding"
    actions = [
      "cognito-idp:DescribeUserPool",
      "cognito-idp:DescribeUserPoolClient",
      "cognito-idp:DescribeUserPoolDomain",
      "cognito-idp:ListUserPoolClients",
      "cognito-idp:GetUICustomization",
      "cognito-idp:SetUICustomization",
      "cognito-idp:DescribeManagedLoginBranding",
      "cognito-idp:DescribeManagedLoginBrandingByClient",
      "cognito-idp:CreateManagedLoginBranding",
      "cognito-idp:UpdateManagedLoginBranding",
    ]
    resources = [var.user_pool_arn]
  }
}

resource "aws_iam_group" "cognito_branding" {
  name = "${var.name}-cognito-branding"
}

resource "aws_iam_group_policy" "cognito_branding" {
  name   = "cognito-dev-branding"
  group  = aws_iam_group.cognito_branding.name
  policy = data.aws_iam_policy_document.cognito_branding.json
}


resource "aws_iam_group" "ocr" {
  name = "${var.name}-ocr"
}

resource "aws_iam_group_policy" "ocr" {
  name  = "textract"
  group = aws_iam_group.ocr.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["textract:AnalyzeExpense", "textract:DetectDocumentText"]
      Resource = "*"
    }]
  })
}

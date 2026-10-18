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
    actions   = ["s3:ListBucket"]
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
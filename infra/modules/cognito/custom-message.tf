locals {
  custom_message_name     = "${var.name}-cognito-custom-message"
  auth_email_identity_arn = "arn:aws:ses:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:identity/${var.auth_email_sender}"
}

# Package only the handler; exclude tests and bytecode from the deployment zip.
data "archive_file" "custom_message" {
  type        = "zip"
  source_file = "${path.module}/../../lambda/cognito_custom_message/handler.py"
  output_path = "${path.root}/.terraform/cognito-custom-message.zip"
}

resource "aws_cloudwatch_log_group" "custom_message" {
  name              = "/aws/lambda/${local.custom_message_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "custom_message" {
  name = "${local.custom_message_name}-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "custom_message_logs" {
  name = "write-custom-message-logs"
  role = aws_iam_role.custom_message.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.custom_message.arn}:*"
    }]
  })
}

resource "aws_lambda_function" "custom_message" {
  function_name    = local.custom_message_name
  role             = aws_iam_role.custom_message.arn
  filename         = data.archive_file.custom_message.output_path
  source_code_hash = data.archive_file.custom_message.output_base64sha256
  handler          = "handler.handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  memory_size      = 128
  timeout          = 3

  depends_on = [aws_iam_role_policy.custom_message_logs]
}

resource "aws_lambda_permission" "cognito_custom_message" {
  statement_id   = "AllowThisUserPool"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.custom_message.function_name
  principal      = "cognito-idp.amazonaws.com"
  source_arn     = aws_cognito_user_pool.this.arn
  source_account = data.aws_caller_identity.current.account_id
}

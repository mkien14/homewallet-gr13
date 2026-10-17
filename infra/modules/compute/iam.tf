data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name}-task-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "api_task" {
  name               = "hw-api-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "api_s3" {
  statement {
    sid       = "PutUploads"
    actions   = ["s3:PutObject"]
    resources = ["${var.receipts_bucket_arn}/receipts/uploads/*"]
  }
  statement {
    sid       = "ReadReceipts"
    actions   = ["s3:GetObject"]
    resources = ["${var.receipts_bucket_arn}/receipts/*"]
  }
}

resource "aws_iam_role_policy" "api_s3" {
  name   = "s3-receipts"
  role   = aws_iam_role.api_task.id
  policy = data.aws_iam_policy_document.api_s3.json
}

resource "aws_iam_role_policy" "execution_read_secrets" {
  count = length(var.secret_arns) > 0 ? 1 : 0
  name  = "read-task-secrets"
  role  = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = var.secret_arns
    }]
  })
}
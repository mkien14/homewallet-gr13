resource "aws_iam_role" "execution" {
  name               = "${var.name}-migrate-execution-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  count              = var.enable_separate_execution_role ? 1 : 0
}

resource "aws_iam_role_policy_attachment" "execution" {
  role = aws_iam_role.execution[0].name

  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
  count      = var.enable_separate_execution_role ? 1 : 0
}

resource "aws_iam_role_policy" "execution_read_db_secret" {
  name  = "read-migration-db-secret"
  role  = aws_iam_role.execution[0].id
  count = var.enable_separate_execution_role ? 1 : 0

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = var.db_secret_arn
    }]
  })
}

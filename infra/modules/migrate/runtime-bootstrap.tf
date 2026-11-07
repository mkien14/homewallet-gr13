resource "aws_iam_role_policy" "execution_read_runtime_secret" {
  count = var.enable_runtime_bootstrap ? 1 : 0

  name = "read-runtime-secret-for-bootstrap"
  role = aws_iam_role.execution[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = var.runtime_db_secret_arn
    }]
  })
}

resource "aws_cloudwatch_log_group" "runtime_bootstrap" {
  count = var.enable_runtime_bootstrap ? 1 : 0

  name              = "/ecs/hw-db-runtime-bootstrap"
  retention_in_days = 14
}

resource "aws_ecs_task_definition" "runtime_bootstrap" {
  count = var.enable_runtime_bootstrap ? 1 : 0

  family                   = "hw-db-runtime-bootstrap"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512

  execution_role_arn = aws_iam_role.execution[0].arn
  task_role_arn      = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "bootstrap"
    image     = var.image
    essential = true

    command = ["python", "-m", "jobs.bootstrap_runtime_db"]

    environment = [
      { name = "DB_HOST", value = var.db_host },
      { name = "DB_PORT", value = "3306" },
      { name = "DB_NAME", value = "homewallet" },
      { name = "DB_SSL_CA", value = "/etc/ssl/rds-global-bundle.pem" },
    ]

    secrets = [
      {
        name      = "DB_USER"
        valueFrom = "${var.db_secret_arn}:username::"
      },
      {
        name      = "DB_PASSWORD"
        valueFrom = "${var.db_secret_arn}:password::"
      },
      {
        name      = "RUNTIME_DB_PASSWORD"
        valueFrom = "${var.runtime_db_secret_arn}:password::"
      },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.runtime_bootstrap[0].name
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = "bootstrap"
      }
    }
  }])

  lifecycle {
    precondition {
      condition     = var.runtime_db_secret_arn != null
      error_message = "Runtime bootstrap requires a runtime DB secret ARN."
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.execution,
    aws_iam_role_policy.execution_read_db_secret,
    aws_iam_role_policy.execution_read_runtime_secret,
  ]
}

data "aws_region" "current" {}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task" {
  name               = "hw-migrate-task-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_cloudwatch_log_group" "migrate" {
  name              = "/ecs/hw-migrate"
  retention_in_days = 14
}

resource "aws_ecs_task_definition" "migrate" {
  family                   = "hw-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "migrate"
    image     = var.image
    essential = true
    command   = ["python", "jobs/migrate.py"]
    environment = [
      { name = "DB_HOST", value = var.db_host },
      { name = "DB_PORT", value = "3306" },
    ]
    secrets = [
      { name = "DB_USER", valueFrom = "${var.db_secret_arn}:username::" },
      { name = "DB_PASSWORD", valueFrom = "${var.db_secret_arn}:password::" },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.migrate.name
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = "migrate"
      }
    }
  }])
}
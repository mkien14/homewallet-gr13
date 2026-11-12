resource "aws_cloudwatch_log_group" "worker" {
  name              = "${local.log_prefix}worker"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.prefix}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory

  execution_role_arn = aws_iam_role.execution.arn
  task_role_arn      = aws_iam_role.worker_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name        = "worker"
      image       = var.worker_image
      essential   = true
      stopTimeout = 30

      command = ["python", "-m", "jobs.worker"]

      environment = [
        for k, v in var.worker_environment : {
          name  = k
          value = v
        }
      ]

      secrets = [
        for k, v in var.worker_secrets : {
          name      = k
          valueFrom = v
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"

        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker.name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "worker" {
  count           = var.autoscaling_enabled ? 0 : 1
  name            = "worker"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.worker.arn

  desired_count    = 1
  launch_type      = "FARGATE"
  platform_version = "1.4.0"

  # Dừng worker cũ trước khi chạy worker mới để tránh chạy song song.
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  network_configuration {
    subnets          = var.app_subnet_ids
    security_groups  = [var.sg_app_id]
    assign_public_ip = false
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [
    aws_iam_role_policy.worker,
    aws_iam_role_policy.execution_read_secrets,
    aws_iam_role_policy_attachment.execution
  ]
}
resource "aws_ecs_service" "worker_release" {
  count = var.autoscaling_enabled ? 1 : 0
  lifecycle { ignore_changes = [task_definition] }
  name            = "worker"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.worker.arn

  desired_count    = 1
  launch_type      = "FARGATE"
  platform_version = "1.4.0"

  # Dừng worker cũ trước khi chạy worker mới để tránh chạy song song.
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  network_configuration {
    subnets          = var.app_subnet_ids
    security_groups  = [var.sg_app_id]
    assign_public_ip = false
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [
    aws_iam_role_policy.worker,
    aws_iam_role_policy.execution_read_secrets,
    aws_iam_role_policy_attachment.execution
  ]
}
moved {
  from = aws_ecs_service.worker
  to   = aws_ecs_service.worker[0]
}

data "aws_region" "current" {}

resource "aws_cloudwatch_log_group" "api" {
  name              = "${local.log_prefix}api"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_cluster" "this" {
  name = local.legacy ? "homewallet" : var.name
  dynamic "setting" {
    for_each = var.autoscaling_enabled ? [1] : []
    content {
      name  = "containerInsights"
      value = "enabled"
    }
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.prefix}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.api_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name         = "api"
    image        = var.image
    essential    = true
    stopTimeout  = 30
    portMappings = [{ containerPort = var.container_port, protocol = "tcp" }]
    environment  = [for k, v in var.api_environment : { name = k, value = v }]
    secrets      = [for k, v in var.api_secrets : { name = k, valueFrom = v }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = "api"
      }
    }
  }])
}

resource "aws_ecs_service" "api" {
  count                              = var.autoscaling_enabled ? 0 : 1
  name                               = "api"
  cluster                            = aws_ecs_cluster.this.id
  task_definition                    = aws_ecs_task_definition.api.arn
  desired_count                      = var.desired_count
  launch_type                        = "FARGATE"
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  health_check_grace_period_seconds = 30

  network_configuration {
    subnets          = var.app_subnet_ids
    security_groups  = [var.sg_app_id, var.sg_api_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = var.container_port
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener.http, aws_lb_listener.https, aws_lb_listener_rule.cloudfront_only, aws_iam_role_policy.execution_read_secrets]
}

resource "aws_ecs_service" "api_scaled" {
  availability_zone_rebalancing      = "ENABLED"
  count                              = var.autoscaling_enabled ? 1 : 0
  name                               = "api"
  cluster                            = aws_ecs_cluster.this.id
  task_definition                    = aws_ecs_task_definition.api.arn
  desired_count                      = var.desired_count
  launch_type                        = "FARGATE"
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  health_check_grace_period_seconds = 30

  network_configuration {
    subnets          = var.app_subnet_ids
    security_groups  = [var.sg_app_id, var.sg_api_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = var.container_port
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    # The approved release workflow and autoscaling own these attributes.
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [aws_lb_listener.http, aws_lb_listener.https, aws_lb_listener_rule.cloudfront_only, aws_iam_role_policy.execution_read_secrets]
}

# Preserve Terraform control of DEV desired_count while autoscaling owns PROD.
resource "aws_appautoscaling_target" "api" {
  count              = var.autoscaling_enabled ? 1 : 0
  min_capacity       = var.autoscaling_min
  max_capacity       = var.autoscaling_max
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.api_scaled[0].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "api_cpu" {
  count              = var.autoscaling_enabled ? 1 : 0
  name               = "${var.name}-api-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api[0].resource_id
  scalable_dimension = aws_appautoscaling_target.api[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.api[0].service_namespace
  target_tracking_scaling_policy_configuration {
    target_value       = 60
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

moved {
  from = aws_ecs_service.api
  to   = aws_ecs_service.api[0]
}

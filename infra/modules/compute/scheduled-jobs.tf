data "aws_caller_identity" "scheduled_jobs" {}

resource "aws_cloudwatch_log_group" "jobs" {
  name              = "/ecs/hw-jobs"
  retention_in_days = 14
}

resource "aws_scheduler_schedule_group" "jobs" {
  name = "${var.name}-jobs"
}

resource "aws_iam_role" "weekly_report_task" {
  name               = "hw-weekly-report-task-role"
  assume_role_policy = data.aws_iam_policy_document.worker_assume.json
}

data "aws_iam_policy_document" "weekly_report_ses" {
  statement {
    sid       = "SendFromVerifiedHomeWalletIdentity"
    actions   = ["ses:SendEmail"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "ses:FromAddress"
      values   = [var.ses_from_address]
    }
  }
}

resource "aws_iam_role_policy" "weekly_report_ses" {
  name   = "ses-send-scheduled-jobs"
  role   = aws_iam_role.weekly_report_task.id
  policy = data.aws_iam_policy_document.weekly_report_ses.json
}

resource "aws_ecs_task_definition" "jobs" {
  family                   = "hw-jobs"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.weekly_report_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name        = "jobs"
    image       = var.jobs_image
    essential   = true
    stopTimeout = 120
    command     = ["python", "-m", "jobs.weekly_report"]
    environment = [for k, v in var.jobs_environment : { name = k, value = v }]
    secrets     = [for k, v in var.jobs_secrets : { name = k, valueFrom = v }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.jobs.name
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = "scheduled"
      }
    }
  }])
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.scheduled_jobs.account_id]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [aws_scheduler_schedule_group.jobs.arn]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.name}-scheduler-ecs-role"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler_run_jobs" {
  statement {
    sid       = "RunScheduledJobTasks"
    actions   = ["ecs:RunTask"]
    resources = [aws_ecs_task_definition.jobs.arn]

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.this.arn]
    }
  }

  statement {
    sid = "PassOnlyJobTaskRolesToECS"
    actions = [
      "iam:PassRole"
    ]
    resources = [
      aws_iam_role.execution.arn,
      aws_iam_role.weekly_report_task.arn
    ]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "scheduler_run_jobs" {
  name   = "run-homewallet-scheduled-jobs"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler_run_jobs.json
}

locals {
  scheduled_jobs = {
    recurring_reminders = {
      name                = "hw-recurring-reminders"
      schedule_expression = "cron(45 7 * * ? *)"
      command             = ["python", "-m", "jobs.recurring_alerts", "reminders"]
    }
    budget_alerts = {
      name                = "hw-budget-alerts"
      schedule_expression = "cron(0 20 * * ? *)"
      command             = ["python", "-m", "jobs.recurring_alerts", "budget-alerts"]
    }
    weekly_report = {
      name                = "hw-weekly-report"
      schedule_expression = "cron(0 8 ? * MON *)"
      command             = ["python", "-m", "jobs.weekly_report"]
    }
  }
}

resource "aws_scheduler_schedule" "jobs" {
  for_each = local.scheduled_jobs

  name                         = each.value.name
  group_name                   = aws_scheduler_schedule_group.jobs.name
  schedule_expression          = each.value.schedule_expression
  schedule_expression_timezone = "Asia/Ho_Chi_Minh"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.this.arn
    role_arn = aws_iam_role.scheduler.arn
    input = jsonencode({
      containerOverrides = [{
        name    = "jobs"
        command = each.value.command
      }]
    })

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.jobs.arn
      launch_type         = "FARGATE"
      platform_version    = "1.4.0"
      task_count          = 1

      network_configuration {
        subnets          = var.app_subnet_ids
        security_groups  = [var.sg_app_id]
        assign_public_ip = false
      }
    }

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 2
    }
  }

  depends_on = [
    aws_iam_role_policy.scheduler_run_jobs,
    aws_iam_role_policy.weekly_report_ses,
    aws_iam_role_policy.execution_read_secrets,
    aws_iam_role_policy_attachment.execution
  ]
}

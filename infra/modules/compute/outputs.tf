output "alb_dns_name" { value = aws_lb.this.dns_name }
output "identities" {
  value = {
    cluster  = aws_ecs_cluster.this.name
    families = [aws_ecs_task_definition.api.family, aws_ecs_task_definition.worker.family, aws_ecs_task_definition.jobs.family]
    logs     = [aws_cloudwatch_log_group.api.name, aws_cloudwatch_log_group.worker.name, aws_cloudwatch_log_group.jobs.name]
    roles    = [aws_iam_role.api_task.name, aws_iam_role.worker_task.name, aws_iam_role.weekly_report_task.name]
  }
}
output "target_group_arn_suffix" { value = aws_lb_target_group.api.arn_suffix }
output "cluster_name" { value = aws_ecs_cluster.this.name }
output "service_name" { value = var.autoscaling_enabled ? aws_ecs_service.api_scaled[0].name : aws_ecs_service.api[0].name }
output "execution_role_arn" { value = aws_iam_role.execution.arn }
output "execution_role_name" { value = aws_iam_role.execution.name }

output "worker_service_name" {
  value = var.autoscaling_enabled ? aws_ecs_service.worker_release[0].name : aws_ecs_service.worker[0].name
}

output "worker_task_definition_arn" {
  value = aws_ecs_task_definition.worker.arn
}

output "jobs_task_definition_arn" {
  value = aws_ecs_task_definition.jobs.arn
}

output "scheduled_job_names" {
  value = { for key, schedule in merge(aws_scheduler_schedule.jobs, aws_scheduler_schedule.jobs_release) : key => schedule.name }
}

output "alb_arn_suffix" {
  value = aws_lb.this.arn_suffix
}

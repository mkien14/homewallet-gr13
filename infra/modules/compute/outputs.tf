output "alb_dns_name" { value = aws_lb.this.dns_name }
output "cluster_name" { value = aws_ecs_cluster.this.name }
output "service_name" { value = aws_ecs_service.api.name }
output "execution_role_arn" { value = aws_iam_role.execution.arn }
output "execution_role_name" { value = aws_iam_role.execution.name }

output "worker_service_name" {
  value = aws_ecs_service.worker.name
}

output "worker_task_definition_arn" {
  value = aws_ecs_task_definition.worker.arn
}

output "jobs_task_definition_arn" {
  value = aws_ecs_task_definition.jobs.arn
}

output "scheduled_job_names" {
  value = { for key, schedule in aws_scheduler_schedule.jobs : key => schedule.name }
}

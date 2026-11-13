output "queue_url" {
  value = aws_sqs_queue.main.id
}
output "queue_name" { value = aws_sqs_queue.main.name }

output "queue_arn" {
  value = aws_sqs_queue.main.arn
}

output "dlq_url" {
  value = aws_sqs_queue.dlq.id
}

output "dlq_arn" {
  value = aws_sqs_queue.dlq.arn
}
output "dlq_name" {
  value = aws_sqs_queue.dlq.name
}

output "production_queue_url" { value = try(aws_sqs_queue.production[0].id, null) }
output "production_queue_arn" { value = try(aws_sqs_queue.production[0].arn, null) }

resource "aws_sns_topic" "operations" { name = "homewallet-prod-operations" }
resource "aws_sns_topic_subscription" "email" {
  for_each  = var.operations_emails
  topic_arn = aws_sns_topic.operations.arn
  protocol  = "email"
  endpoint  = each.value
}
locals {
  # name => [namespace, metric, statistic, comparison, threshold, dimensions, missing]
  alarms = merge({
    target_5xx      = ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "Sum", "GreaterThanOrEqualToThreshold", 5, { LoadBalancer = module.compute.alb_arn_suffix, TargetGroup = module.compute.target_group_arn_suffix }, "notBreaching"]
    unhealthy       = ["AWS/ApplicationELB", "UnHealthyHostCount", "Maximum", "GreaterThanOrEqualToThreshold", 1, { LoadBalancer = module.compute.alb_arn_suffix, TargetGroup = module.compute.target_group_arn_suffix }, "breaching"]
    healthy_min     = ["AWS/ApplicationELB", "HealthyHostCount", "Minimum", "LessThanThreshold", 2, { LoadBalancer = module.compute.alb_arn_suffix, TargetGroup = module.compute.target_group_arn_suffix }, "breaching"]
    api_tasks       = ["ECS/ContainerInsights", "RunningTaskCount", "Minimum", "LessThanThreshold", 2, { ClusterName = module.compute.cluster_name, ServiceName = "api" }, "breaching"]
    worker_tasks    = ["ECS/ContainerInsights", "RunningTaskCount", "Minimum", "LessThanThreshold", 1, { ClusterName = module.compute.cluster_name, ServiceName = "worker" }, "breaching"]
    rds_cpu         = ["AWS/RDS", "CPUUtilization", "Average", "GreaterThanThreshold", 80, { DBInstanceIdentifier = module.data.identifier }, "breaching"]
    rds_storage     = ["AWS/RDS", "FreeStorageSpace", "Minimum", "LessThanThreshold", 4294967296, { DBInstanceIdentifier = module.data.identifier }, "breaching"]
    rds_memory      = ["AWS/RDS", "FreeableMemory", "Minimum", "LessThanThreshold", 268435456, { DBInstanceIdentifier = module.data.identifier }, "breaching"]
    rds_connections = ["AWS/RDS", "DatabaseConnections", "Maximum", "GreaterThanThreshold", 100, { DBInstanceIdentifier = module.data.identifier }, "missing"]
    dlq_messages    = ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "Maximum", "GreaterThanOrEqualToThreshold", 1, { QueueName = module.queue.dlq_name }, "notBreaching"]
    dlq_age         = ["AWS/SQS", "ApproximateAgeOfOldestMessage", "Maximum", "GreaterThanThreshold", 300, { QueueName = module.queue.dlq_name }, "notBreaching"]
    worker_stall    = ["AWS/SQS", "ApproximateAgeOfOldestMessage", "Maximum", "GreaterThanThreshold", 600, { QueueName = module.queue.queue_name }, "notBreaching"]
    }, {
    for i, id in module.network.nat_gateway_ids : "nat_${i}_errors" => ["AWS/NATGateway", "ErrorPortAllocation", "Sum", "GreaterThanThreshold", 0, { NatGatewayId = id }, "notBreaching"]
    }, {
    for i, id in module.network.nat_gateway_ids : "nat_${i}_drops" => ["AWS/NATGateway", "PacketsDropCount", "Sum", "GreaterThanThreshold", 100, { NatGatewayId = id }, "notBreaching"]
    }, {
    for i in range(2) : "redis_${i}_cpu" => ["AWS/ElastiCache", "EngineCPUUtilization", "Maximum", "GreaterThanThreshold", 80, { CacheClusterId = module.cache.member_cluster_ids[i], CacheNodeId = "0001" }, "breaching"]
    }, {
  for i in range(2) : "redis_${i}_replication" => ["AWS/ElastiCache", "ReplicationLag", "Maximum", "GreaterThanThreshold", 5, { CacheClusterId = module.cache.member_cluster_ids[i], CacheNodeId = "0001" }, "notBreaching"] })
}
resource "aws_cloudwatch_metric_alarm" "operations" {
  for_each            = local.alarms
  alarm_name          = "homewallet-prod-${each.key}"
  namespace           = each.value[0]
  metric_name         = each.value[1]
  statistic           = each.value[2]
  comparison_operator = each.value[3]
  threshold           = each.value[4]
  dimensions          = each.value[5]
  treat_missing_data  = each.value[6]
  period              = 60
  evaluation_periods  = 3
  datapoints_to_alarm = 2
  alarm_actions       = [aws_sns_topic.operations.arn]
  ok_actions          = [aws_sns_topic.operations.arn]
}
resource "aws_cloudwatch_dashboard" "operations" {
  dashboard_name = "homewallet-prod-operations"
  dashboard_body = jsonencode({ widgets = [for i, key in sort(keys(local.alarms)) : {
    type = "metric", x = (i % 2) * 12, y = floor(i / 2) * 6, width = 12, height = 6
    properties = {
      title   = key, region = "ap-southeast-1", view = "timeSeries", period = 60, stat = local.alarms[key][2]
      metrics = [concat([local.alarms[key][0], local.alarms[key][1]], flatten([for k, v in local.alarms[key][5] : [k, v]]))]
    }
  }] })
}
resource "aws_cloudwatch_event_rule" "deployment_failure" {
  name          = "homewallet-prod-deployment-failure"
  event_pattern = jsonencode({ source = ["aws.ecs"], "detail-type" = ["ECS Deployment State Change"], detail = { eventName = ["SERVICE_DEPLOYMENT_FAILED"], clusterArn = ["arn:aws:ecs:ap-southeast-1:${var.expected_account_id}:cluster/homewallet-prod"] } })
}
resource "aws_cloudwatch_event_target" "deployment_failure" {
  rule       = aws_cloudwatch_event_rule.deployment_failure.name
  arn        = aws_sns_topic.operations.arn
  role_arn   = aws_iam_role.deployment_events.arn
  depends_on = [aws_iam_role_policy.deployment_events]
}
resource "aws_iam_role" "deployment_events" {
  name = "homewallet-prod-deployment-events"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "events.amazonaws.com" }, Action = "sts:AssumeRole", Condition = {
      StringEquals = { "aws:SourceAccount" = var.expected_account_id }
      ArnEquals    = { "aws:SourceArn" = aws_cloudwatch_event_rule.deployment_failure.arn }
    } }]
  })
}
resource "aws_iam_role_policy" "deployment_events" {
  role   = aws_iam_role.deployment_events.id
  name   = "publish-production-deployment-events"
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sns:Publish", Resource = aws_sns_topic.operations.arn }] })
}
resource "aws_sns_topic_policy" "events" {
  arn = aws_sns_topic.operations.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Principal = { Service = "events.rds.amazonaws.com" }, Action = "sns:Publish", Resource = aws_sns_topic.operations.arn, Condition = {
        StringEquals = { "aws:SourceAccount" = var.expected_account_id }
        ArnEquals    = { "aws:SourceArn" = "arn:aws:rds:ap-southeast-1:${var.expected_account_id}:db:${module.data.identifier}" }
      } }
    ]
  })
}
resource "aws_db_event_subscription" "failover" {
  name             = "homewallet-prod-rds-events"
  sns_topic        = aws_sns_topic.operations.arn
  source_type      = "db-instance"
  source_ids       = [module.data.identifier]
  event_categories = ["failover", "failure", "low storage", "availability"]
  depends_on       = [aws_sns_topic_policy.events]
}
resource "aws_budgets_budget" "production" {
  name         = "homewallet-prod-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  cost_filter {
    name   = "TagKeyValue"
    values = ["user:env$prod"]
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.operations_emails
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.operations_emails
  }
}

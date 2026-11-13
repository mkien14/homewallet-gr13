# Week 10 #33: review costs independently of the WAF #31 budget before apply.
resource "aws_sns_topic" "operations" {
  name = "homewallet-dev-operations"
}

resource "aws_sns_topic_subscription" "operations_email" {
  topic_arn = aws_sns_topic.operations.arn
  protocol  = "email"
  endpoint  = "homewallet26@gmail.com"
}

locals {
  operational_alarms = merge(
    var.enable_api_https_gateway ? {
      api_gateway_5xx = {
        namespace   = "AWS/ApiGateway", metric = "5xx"
        dimensions  = { ApiId = module.api_https[0].api_id }
        statistic   = "Sum", period = 60, threshold = 5
        comparison  = "GreaterThanOrEqualToThreshold", evaluation = 3, datapoints = 2
        missing     = "notBreaching"
        description = "Public HTTP API 5xx including integration errors; ALB metrics no longer cover this traffic."
      }
      api_gateway_latency = {
        namespace   = "AWS/ApiGateway", metric = "IntegrationLatency"
        dimensions  = { ApiId = module.api_https[0].api_id }
        statistic   = "Average", period = 60, threshold = 1000
        comparison  = "GreaterThanOrEqualToThreshold", evaluation = 3, datapoints = 3
        missing     = "notBreaching"
        description = "Public HTTP API integration latency averages at least one second for three minutes."
      }
    } : {},
    {
      dlq_visible = {
        namespace   = "AWS/SQS", metric = "ApproximateNumberOfMessagesVisible"
        dimensions  = { QueueName = module.queue.dlq_name }
        statistic   = "Maximum", period = 300, threshold = 1
        comparison  = "GreaterThanOrEqualToThreshold", evaluation = 1, datapoints = 1
        missing     = "notBreaching"
        description = "DLQ has visible messages; missing data alone does not prove queue health."
      }
      alb_5xx = {
        namespace   = "AWS/ApplicationELB", metric = "HTTPCode_ELB_5XX_Count"
        dimensions  = { LoadBalancer = module.compute.alb_arn_suffix }
        statistic   = "Sum", period = 60, threshold = 5
        comparison  = "GreaterThanOrEqualToThreshold", evaluation = 3, datapoints = 2
        missing     = "notBreaching"
        description = "ALB-generated 5xx, not application target 5xx."
      }
      rds_cpu = {
        namespace   = "AWS/RDS", metric = "CPUUtilization"
        dimensions  = { DBInstanceIdentifier = module.data.identifier }
        statistic   = "Average", period = 300, threshold = 80
        comparison  = "GreaterThanOrEqualToThreshold", evaluation = 3, datapoints = 3
        missing     = "missing"
        description = "RDS CPU at or above 80 percent for three periods."
      }
      rds_storage = {
        namespace   = "AWS/RDS", metric = "FreeStorageSpace"
        dimensions  = { DBInstanceIdentifier = module.data.identifier }
        statistic   = "Minimum", period = 300, threshold = 2147483648
        comparison  = "LessThanThreshold", evaluation = 1, datapoints = 1
        missing     = "missing"
        description = "Free storage below 2 GiB. Proposed evaluation: one 5-minute period; review before apply."
      }
    },
    {
      for alarm in flatten([
        # Keep monitoring-only plans independent of ECS task definitions.
        for service, service_name in {
          api    = "api"
          worker = "worker"
          } : [
          for label, metric in { cpu = "CPUUtilization", memory = "MemoryUtilization" } : {
            key                      = "${service}_${label}"
            config = {
              namespace   = "AWS/ECS", metric = metric
              dimensions  = { ClusterName = module.compute.cluster_name, ServiceName = service_name }
              statistic   = "Average", period = 300, threshold = 80
              comparison  = "GreaterThanOrEqualToThreshold", evaluation = 3, datapoints = 3
              missing     = "missing"
              description = "${service} ${label} at or above 80 percent for three periods."
            }
          }
        ]
      ]) : alarm.key => alarm.config
    }
  )
}

resource "aws_cloudwatch_metric_alarm" "operations" {
  for_each = local.operational_alarms

  alarm_name          = "homewallet-dev-${replace(each.key, "_", "-")}"
  alarm_description   = each.value.description
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  dimensions          = each.value.dimensions
  statistic           = each.value.statistic
  period              = each.value.period
  comparison_operator = each.value.comparison
  threshold           = each.value.threshold
  evaluation_periods  = each.value.evaluation
  datapoints_to_alarm = each.value.datapoints
  treat_missing_data  = each.value.missing

  alarm_actions = [aws_sns_topic.operations.arn]
}

resource "aws_cloudwatch_dashboard" "operations" {
  dashboard_name = "homewallet-dev-operations"

  dashboard_body = jsonencode({
    widgets = [for index, key in sort(keys(local.operational_alarms)) : {
      type   = "metric"
      x      = (index % 2) * 12
      y      = floor(index / 2) * 6
      width  = 12
      height = 6
      properties = {
        title  = "${key} | ap-southeast-1 | ${local.operational_alarms[key].period}s"
        region = "ap-southeast-1"
        view   = "timeSeries"
        period = local.operational_alarms[key].period
        stat   = local.operational_alarms[key].statistic
        metrics = [concat(
          [local.operational_alarms[key].namespace, local.operational_alarms[key].metric],
          flatten([for name, value in local.operational_alarms[key].dimensions : [name, value]])
        )]
      }
    }]
  })
}

output "operations_sns_topic_arn" {
  value = aws_sns_topic.operations.arn
}

output "operations_alarm_names" {
  value = { for key, alarm in aws_cloudwatch_metric_alarm.operations : key => alarm.alarm_name }
}

data "aws_caller_identity" "current" {}


resource "aws_sqs_queue" "dlq" {

  name = "${var.name_prefix}receipts-dlq"

  message_retention_seconds = 1209600 # 14 ngày

  sqs_managed_sse_enabled = true

}


resource "aws_sqs_queue" "main" {

  name                       = "${var.name_prefix}receipts-queue"
  receive_wait_time_seconds  = 20
  visibility_timeout_seconds = 180
  sqs_managed_sse_enabled    = true # SSE-SQS, KHÔNG dùng khóa KMS do AWS quản lý
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3

  })
}


data "aws_iam_policy_document" "s3_to_sqs" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.main.arn]
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = [var.bucket_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }

}


resource "aws_sqs_queue_policy" "main" {
  queue_url = aws_sqs_queue.main.id
  policy    = data.aws_iam_policy_document.s3_to_sqs.json

}


resource "aws_s3_bucket_notification" "receipts" {
  bucket = var.bucket_id
  queue {
    queue_arn     = aws_sqs_queue.main.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "receipts/uploads/"
  }
  dynamic "queue" {
    for_each = var.production_ocr_enabled ? [1] : []
    content {
      queue_arn     = aws_sqs_queue.production[0].arn
      events        = ["s3:ObjectCreated:*"]
      filter_prefix = "receipts/production/"
    }
  }
  depends_on = [aws_sqs_queue_policy.main, aws_sqs_queue_policy.production]

}

resource "aws_sqs_queue" "production_dlq" {
  count                     = var.production_ocr_enabled ? 1 : 0
  name                      = "${var.name_prefix}production-ocr-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
  lifecycle { prevent_destroy = true }
}

resource "aws_sqs_queue" "production" {
  count                      = var.production_ocr_enabled ? 1 : 0
  name                       = "${var.name_prefix}production-ocr-queue"
  receive_wait_time_seconds  = 20
  visibility_timeout_seconds = 180
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.production_dlq[0].arn
    maxReceiveCount     = 3
  })
  lifecycle { prevent_destroy = true }
}

resource "aws_sqs_queue_policy" "production" {
  count     = var.production_ocr_enabled ? 1 : 0
  queue_url = aws_sqs_queue.production[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "s3.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.production[0].arn
      Condition = {
        ArnEquals    = { "aws:SourceArn" = var.bucket_arn }
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
      }
    }]
  })
}

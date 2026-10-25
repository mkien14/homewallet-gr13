data "aws_caller_identity" "current" {}


resource "aws_sqs_queue" "dlq" {

  name = "receipts-dlq"

  message_retention_seconds = 1209600 # 14 ngày

  sqs_managed_sse_enabled = true

}


resource "aws_sqs_queue" "main" {

  name                       = "receipts-queue"
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
  depends_on = [aws_sqs_queue_policy.main]

}
data "aws_caller_identity" "worker" {}

data "aws_iam_policy_document" "worker_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.worker.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values = [
        "arn:aws:ecs:${data.aws_region.current.name}:${data.aws_caller_identity.worker.account_id}:*"
      ]
    }
  }
}

resource "aws_iam_role" "worker_task" {
  name               = "hw-worker-task-role"
  assume_role_policy = data.aws_iam_policy_document.worker_assume.json
}

# Bucket receipts hiện dùng SSE-KMS với khóa mặc định aws/s3.
data "aws_kms_key" "receipts" {
  key_id = "alias/aws/s3"
}

data "aws_iam_policy_document" "worker" {
  statement {
    sid = "ConsumeReceiptsQueue"

    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ChangeMessageVisibility"
    ]

    resources = [var.worker_queue_arn]
  }

  statement {
    sid       = "ReadReceiptUploads"
    actions   = ["s3:GetObject"]
    resources = ["${var.receipts_bucket_arn}/receipts/uploads/*"]
  }

  statement {
    sid       = "WriteParsedReceipts"
    actions   = ["s3:PutObject"]
    resources = ["${var.receipts_bucket_arn}/receipts/parsed/*"]
  }

  statement {
    sid = "UseReceiptsEncryptionKey"

    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey"
    ]

    resources = [data.aws_kms_key.receipts.arn]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3.${data.aws_region.current.name}.amazonaws.com"]
    }
  }

  statement {
    sid       = "PublishMetrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "worker" {
  name   = "worker-receipts"
  role   = aws_iam_role.worker_task.id
  policy = data.aws_iam_policy_document.worker.json
}
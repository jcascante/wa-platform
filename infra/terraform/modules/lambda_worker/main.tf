# SQS-triggered worker Lambda. ReportBatchItemFailures means one bad message in a batch is
# retried/DLQ'd on its own instead of the whole batch being redelivered (see
# lambda_handlers/worker_handler.py — it returns batchItemFailures explicitly for this reason).

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = "${var.name}-worker-lambda"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy_attachment" "basic" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "vpc" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "inline" {
  statement {
    actions   = ["kms:Encrypt", "kms:Decrypt"]
    resources = [var.kms_key_arn]
  }
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.database_url_secret_arn, var.meta_app_secret_arn]
  }
  statement {
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [var.queue_arn]
  }
}

resource "aws_iam_role_policy" "inline" {
  name   = "${var.name}-worker-lambda-inline"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.inline.json
}

resource "aws_lambda_function" "this" {
  function_name    = "${var.name}-worker"
  role             = aws_iam_role.this.arn
  handler          = "wa_platform.lambda_handlers.worker_handler.handler"
  runtime          = "python3.12"
  timeout          = 45 # > tenant webhook call's own 30s budget
  memory_size      = 256
  filename         = var.package_path
  source_code_hash = filebase64sha256(var.package_path)

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [var.security_group_id]
  }

  environment {
    variables = {
      ENVIRONMENT         = var.environment
      DATABASE_URL_SECRET = var.database_url_secret_arn
      META_APP_SECRET_ARN = var.meta_app_secret_arn
      KMS_KEY_ID          = var.kms_key_id
      SQS_QUEUE_URL       = var.queue_url
      AWS_REGION          = var.aws_region
    }
  }
}

resource "aws_lambda_event_source_mapping" "sqs" {
  event_source_arn        = var.queue_arn
  function_name           = aws_lambda_function.this.arn
  batch_size              = 5
  function_response_types = ["ReportBatchItemFailures"]
}

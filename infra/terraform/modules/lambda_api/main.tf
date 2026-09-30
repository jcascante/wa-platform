# API Gateway HTTP API (cheaper than REST API) fronting a single Lambda running the FastAPI
# app via Mangum. Pay-per-request on both sides — no idle cost, the whole point of starting
# on Lambda instead of ECS/EKS.

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
  name               = "${var.name}-api-lambda"
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
    actions   = ["sqs:SendMessage"]
    resources = [var.queue_arn]
  }
}

resource "aws_iam_role_policy" "inline" {
  name   = "${var.name}-api-lambda-inline"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.inline.json
}

# Created explicitly (instead of letting Lambda auto-create it on first invoke) so it has a
# retention period from day one — otherwise these logs are kept forever at growing cost.
resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.name}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "this" {
  function_name    = "${var.name}-api"
  role             = aws_iam_role.this.arn
  handler          = "wa_platform.lambda_handlers.api_handler.handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 256
  filename         = var.package_path
  source_code_hash = filebase64sha256(var.package_path)
  # Caps concurrent executions so a traffic burst can't open more DB connections than
  # db.t4g.micro can handle across api + worker combined — see modules/lambda_worker for its
  # half of the budget.
  reserved_concurrent_executions = var.reserved_concurrent_executions

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
      # AWS_REGION is a reserved Lambda env var name (Terraform apply fails if you set it) — the
      # runtime injects it automatically, and Settings.aws_region already defaults from it.
    }
  }

  depends_on = [aws_cloudwatch_log_group.this]
}

resource "aws_apigatewayv2_api" "this" {
  name          = "${var.name}-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.this.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true

  # No auth-specific rate limiting exists yet (e.g. per-IP login attempts) — this is a blunt,
  # global cap that at least stops an unthrottled flood from running up the Lambda/RDS bill or
  # exhausting connections. Revisit with a WAF rate-based rule or a per-route limit if
  # login/register specifically need tighter limits than the rest of the API.
  default_route_settings {
    throttling_burst_limit = 20
    throttling_rate_limit  = 10
  }
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}

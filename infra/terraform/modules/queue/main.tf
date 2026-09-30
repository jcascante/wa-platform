# Plain SQS, no broker to run — cheapest async pipeline for v1 (SPEC §10/§13 left this open).
# DLQ catches messages the worker Lambda fails 5x in a row (a poison message or a persistent
# tenant/DB issue) so they don't silently vanish or block the rest of the queue.

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name}-inbound-dlq"
  message_retention_seconds = 1209600 # 14 days
}

resource "aws_sqs_queue" "inbound" {
  name = "${var.name}-inbound"
  # 6x the worker Lambda's 75s function timeout (modules/lambda_worker) — SQS best practice is
  # at least the function timeout, and comfortable headroom above it matters more here since a
  # too-short visibility timeout would let a message be picked up again (and reprocessed) by a
  # second invocation while the first is still legitimately running.
  visibility_timeout_seconds = 450
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 5
  })
}

# Alerts when a message lands in the DLQ, i.e. the worker failed on it 5 times in a row (see
# lambda_worker's batchItemFailures handling) — without this, that failure is only discovered by
# accident.
resource "aws_sns_topic" "dlq_alarm" {
  count = var.alert_email != null ? 1 : 0
  name  = "${var.name}-dlq-alarm"
}

resource "aws_sns_topic_subscription" "dlq_alarm_email" {
  count     = var.alert_email != null ? 1 : 0
  topic_arn = aws_sns_topic.dlq_alarm[0].arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  count               = var.alert_email != null ? 1 : 0
  alarm_name          = "${var.name}-dlq-not-empty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }
  alarm_description = "A message landed in the ${var.name} DLQ — the worker failed processing it 5 times."
  alarm_actions     = [aws_sns_topic.dlq_alarm[0].arn]
}

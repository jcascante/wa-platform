# Plain SQS, no broker to run — cheapest async pipeline for v1 (SPEC §10/§13 left this open).
# DLQ catches messages the worker Lambda fails 5x in a row (a poison message or a persistent
# tenant/DB issue) so they don't silently vanish or block the rest of the queue.

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name}-inbound-dlq"
  message_retention_seconds = 1209600 # 14 days
}

resource "aws_sqs_queue" "inbound" {
  name                       = "${var.name}-inbound"
  visibility_timeout_seconds = 60 # > worker's per-message processing budget (30s tenant call + send)
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 5
  })
}

output "queue_url" {
  value = aws_sqs_queue.inbound.url
}

output "queue_arn" {
  value = aws_sqs_queue.inbound.arn
}

output "dlq_arn" {
  value = aws_sqs_queue.dlq.arn
}

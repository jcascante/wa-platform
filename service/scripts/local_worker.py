"""Drains the local SQS queue the same way the worker Lambda does in AWS, so `/webhook` ->
`/onboarding` -> tenant-webhook can be exercised end to end without deploying anything.
`worker_handler.handler` expects a Lambda SQS event shape, so each poll batch is reassembled
into one before being passed straight through — this script never touches message_processor
directly, to stay honest to what actually runs in prod.

Run with: python scripts/local_worker.py  (needs the same env as `make dev` — see .env)
"""

import boto3

from wa_platform.core.config import get_settings
from wa_platform.core.logging import configure_logging, get_logger
from wa_platform.lambda_handlers.worker_handler import handler

configure_logging()
log = get_logger(__name__)


def main() -> None:
    settings = get_settings()
    sqs = boto3.client("sqs", region_name=settings.aws_region, endpoint_url=settings.aws_endpoint_url)
    queue_url = settings.sqs_queue_url
    log.info("local_worker_started", queue_url=queue_url)

    while True:
        resp = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=10,
            MessageAttributeNames=["All"],
        )
        messages = resp.get("Messages", [])
        if not messages:
            continue

        event = {
            "Records": [
                {"messageId": m["MessageId"], "receiptHandle": m["ReceiptHandle"], "body": m["Body"]}
                for m in messages
            ]
        }
        result = handler(event, None)
        failed_ids = {f["itemIdentifier"] for f in result.get("batchItemFailures", [])}

        for m in messages:
            if m["MessageId"] in failed_ids:
                log.warning("message_left_on_queue", message_id=m["MessageId"])
                continue
            sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=m["ReceiptHandle"])
            log.info("message_processed", message_id=m["MessageId"])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

import json

import boto3

from wa_platform.core.config import Settings


class InboundQueue:
    """Queues raw Meta webhook events so the webhook handler can ack within a few seconds
    (SPEC §10) instead of doing dedupe/lookup/forward/send inline. The worker Lambda drains this
    queue and dispatches on `type`."""

    def __init__(self, settings: Settings):
        self._queue_url = settings.sqs_queue_url
        self._client = boto3.client(
            "sqs",
            region_name=settings.aws_region,
            endpoint_url=settings.aws_endpoint_url,
        )

    def enqueue(self, phone_number_id: str, msg_type: str, data: dict) -> None:
        self._client.send_message(
            QueueUrl=self._queue_url,
            MessageBody=json.dumps({"phone_number_id": phone_number_id, "type": msg_type, "data": data}),
        )

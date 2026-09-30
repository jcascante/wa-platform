import asyncio
import json

from wa_platform.core.config import get_settings
from wa_platform.core.logging import configure_logging, get_logger
from wa_platform.core.security import Encryptor
from wa_platform.db.session import get_session_factory
from wa_platform.integrations.meta.client import MetaGraphClient
from wa_platform.workers.message_processor import handle_account_update, handle_message

configure_logging()
log = get_logger(__name__)


def handler(event: dict, context) -> dict:
    """SQS-triggered Lambda. Batch failures are reported individually (partial batch response)
    so a poison message doesn't block the rest of the batch or the whole queue."""
    settings = get_settings()
    session_factory = get_session_factory(settings)  # cached across warm invocations
    encryptor = Encryptor(settings)
    meta = MetaGraphClient(settings)

    failures = []
    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            with session_factory() as db:
                if body["type"] == "message":
                    asyncio.run(
                        handle_message(db, settings, encryptor, meta, body["phone_number_id"], body["data"])
                    )
                elif body["type"] == "account_update":
                    handle_account_update(body["phone_number_id"], body["data"])
        except Exception:
            log.exception("message_processing_failed", message_id=record.get("messageId"))
            failures.append({"itemIdentifier": record["messageId"]})

    return {"batchItemFailures": failures}

import asyncio
import json

from sqlalchemy.orm import Session

from wa_platform.core.config import get_settings
from wa_platform.core.logging import configure_logging, get_logger
from wa_platform.core.security import Encryptor
from wa_platform.db.session import make_engine
from wa_platform.integrations.meta.client import MetaGraphClient
from wa_platform.workers.message_processor import handle_message

configure_logging()
log = get_logger(__name__)


def handler(event: dict, context) -> dict:
    """SQS-triggered Lambda. Batch failures are reported individually (partial batch response)
    so a poison message doesn't block the rest of the batch or the whole queue."""
    settings = get_settings()
    engine = make_engine(settings)
    encryptor = Encryptor(settings)
    meta = MetaGraphClient(settings)

    failures = []
    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            with Session(engine) as db:
                asyncio.run(
                    handle_message(
                        db, settings, encryptor, meta, body["phone_number_id"], body["message"]
                    )
                )
        except Exception:
            log.exception("message_processing_failed", message_id=record.get("messageId"))
            failures.append({"itemIdentifier": record["messageId"]})

    return {"batchItemFailures": failures}

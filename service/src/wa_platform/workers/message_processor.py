from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from wa_platform.core.config import Settings
from wa_platform.core.logging import get_logger
from wa_platform.core.security import Encryptor, sign
from wa_platform.db.models import Message, ProcessedMessage, Tenant
from wa_platform.integrations.meta.client import MetaGraphClient

log = get_logger(__name__)

HISTORY_LIMIT = 20


async def handle_message(
    db: Session,
    settings: Settings,
    encryptor: Encryptor,
    meta: MetaGraphClient,
    phone_number_id: str,
    msg: dict,
) -> None:
    # Dedupe first — Meta retries deliveries, and this insert must land before any side effect.
    inserted = db.execute(
        insert(ProcessedMessage).values(wa_message_id=msg["id"]).on_conflict_do_nothing()
    )
    db.commit()
    if inserted.rowcount == 0:  # type: ignore[attr-defined]  # CursorResult at runtime
        return

    tenant = db.scalar(select(Tenant).where(Tenant.phone_number_id == phone_number_id))
    if not tenant or tenant.status != "active":
        return
    log = get_logger(__name__).bind(tenant_id=tenant.tenant_id)

    token = encryptor.decrypt(tenant.business_token)
    wa_id = msg["from"]
    await meta.mark_read(phone_number_id, token, msg["id"])

    if msg.get("type") != "text":
        await meta.send_text(phone_number_id, token, wa_id, "Sorry, I can only read text messages for now.")
        return

    text = msg["text"]["body"]
    _record(db, tenant.tenant_id, wa_id, "inbound", text)
    reply = await _forward_to_tenant_webhook(db, encryptor, tenant, wa_id, text, log)
    _record(db, tenant.tenant_id, wa_id, "outbound", reply)
    await meta.send_text(phone_number_id, token, wa_id, reply)


def _record(db: Session, tenant_id: str, wa_id: str, direction: str, body: str) -> None:
    db.add(Message(tenant_id=tenant_id, wa_id=wa_id, direction=direction, body=body))
    db.commit()


def _history(db: Session, tenant_id: str, wa_id: str) -> list[dict[str, str]]:
    rows = db.scalars(
        select(Message)
        .where(Message.tenant_id == tenant_id, Message.wa_id == wa_id)
        .order_by(Message.created_at.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    return [
        {"role": "user" if r.direction == "inbound" else "assistant", "content": r.body or ""}
        for r in reversed(rows)
    ]


async def _forward_to_tenant_webhook(
    db, encryptor: Encryptor, tenant: Tenant, wa_id: str, text: str, log
) -> str:
    """Forwards the inbound message to the tenant's own webhook, signed so they can verify it
    came from us. Any network failure, non-2xx, or malformed reply must degrade to an apology
    message rather than propagate — a tenant's broken bot must never break the platform."""
    import json

    import httpx

    if not tenant.webhook_url or not tenant.webhook_secret:
        return "This number isn't connected to a chatbot yet."

    body = json.dumps(
        {
            "tenant_id": tenant.tenant_id,
            "from": wa_id,
            "message": text,
            "history": _history(db, tenant.tenant_id, wa_id),
        }
    ).encode()
    secret = encryptor.decrypt(tenant.webhook_secret)
    sig = sign(body, secret)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                tenant.webhook_url,
                content=body,
                headers={"Content-Type": "application/json", "X-Platform-Signature": sig},
            )
            r.raise_for_status()
            return r.json().get("reply", "")
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.warning("webhook_forward_failed", error=repr(exc))
        return "Sorry, something went wrong on our end. Please try again shortly."

import asyncio
import json
from urllib.parse import urlparse

import httpx
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from wa_platform.core.config import Settings
from wa_platform.core.logging import get_logger
from wa_platform.core.security import Encryptor, sign
from wa_platform.core.ssrf_guard import UnsafeWebhookHost, assert_public_host
from wa_platform.db.models import Message, ProcessedMessage, Tenant
from wa_platform.integrations.meta.client import MetaGraphClient
from wa_platform.schemas.webhook import TenantForwardPayload, TenantForwardReply

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
    wa_message_id = msg.get("id")
    # Dedupe first — Meta retries deliveries, and this insert must land before any side effect a
    # concurrent redelivery of the same message could also trigger. If processing then fails
    # partway through, the row is removed in the `except` below so Meta's retry isn't silently
    # swallowed by the dedupe check on the next delivery attempt.
    #
    # Checked via RETURNING, not cursor.rowcount: psycopg3 (this project's driver) reports -1 for
    # an INSERT ... ON CONFLICT DO NOTHING regardless of whether a row was actually inserted, so
    # `rowcount == 0` never fired — every Meta retry was silently reprocessed from scratch.
    inserted = db.execute(
        insert(ProcessedMessage)
        .values(wa_message_id=wa_message_id)
        .on_conflict_do_nothing()
        .returning(ProcessedMessage.wa_message_id)
    )
    db.commit()
    if inserted.first() is None:
        return

    try:
        await _handle_message_inner(db, encryptor, meta, phone_number_id, msg)
    except Exception:
        db.execute(delete(ProcessedMessage).where(ProcessedMessage.wa_message_id == wa_message_id))
        db.commit()
        raise


def handle_account_update(phone_number_id: str, value: dict) -> None:
    """Meta's account_update webhook (number banned/restricted/etc.) — no defined behavior yet
    (SPEC §13 open questions). Logged so it's at least visible, instead of the KeyError this used
    to hit when routed through handle_message, which expects a message-shaped payload
    (msg["id"]/msg["from"])."""
    log.info("account_update_received", phone_number_id=phone_number_id, event=value.get("event"))


async def _handle_message_inner(
    db: Session,
    encryptor: Encryptor,
    meta: MetaGraphClient,
    phone_number_id: str,
    msg: dict,
) -> None:
    tenant = db.scalar(select(Tenant).where(Tenant.phone_number_id == phone_number_id))
    if not tenant or tenant.status != "active":
        return
    tenant_log = log.bind(tenant_id=tenant.tenant_id)

    token = encryptor.decrypt(tenant.business_token)
    wa_id = msg["from"]
    await meta.mark_read(phone_number_id, token, msg["id"])

    if msg.get("type") != "text":
        await meta.send_text(phone_number_id, token, wa_id, "Sorry, I can only read text messages for now.")
        return

    text = msg["text"]["body"]
    # History must be read before recording this message, or the current turn shows up twice —
    # once as `message`, once as the last entry of `history` — in the payload we forward.
    history = _history(db, tenant.tenant_id, wa_id)
    _record(db, tenant.tenant_id, wa_id, "inbound", text, msg.get("id"))
    reply = await _forward_to_tenant_webhook(encryptor, tenant, wa_id, text, history, tenant_log)
    _record(db, tenant.tenant_id, wa_id, "outbound", reply, None)
    await meta.send_text(phone_number_id, token, wa_id, reply)


def _record(
    db: Session, tenant_id: str, wa_id: str, direction: str, body: str, wa_message_id: str | None
) -> None:
    db.add(
        Message(tenant_id=tenant_id, wa_id=wa_id, direction=direction, body=body, wa_message_id=wa_message_id)
    )
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
    encryptor: Encryptor,
    tenant: Tenant,
    wa_id: str,
    text: str,
    history: list[dict[str, str]],
    log,
) -> str:
    """Forwards the inbound message to the tenant's own webhook, signed so they can verify it
    came from us. Any network failure, non-2xx, malformed/empty reply, or webhook host that
    resolves to internal infrastructure must degrade to an apology message rather than propagate
    — a tenant's broken (or malicious) bot must never break the platform or leak an internal
    response back over WhatsApp."""
    if not tenant.webhook_url or not tenant.webhook_secret:
        return "This number isn't connected to a chatbot yet."

    apology = "Sorry, something went wrong on our end. Please try again shortly."

    host = urlparse(tenant.webhook_url).hostname
    try:
        if host is None:
            raise UnsafeWebhookHost("webhook url has no host")
        # Re-checked here, not just at set-time (schemas/tenant.py) — DNS can resolve somewhere
        # different by the time we actually connect.
        await asyncio.to_thread(assert_public_host, host)
    except UnsafeWebhookHost as exc:
        log.warning("webhook_url_unsafe", error=str(exc))
        return apology

    body = json.dumps(
        TenantForwardPayload(tenant_id=tenant.tenant_id, from_=wa_id, message=text, history=history).to_wire()
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
            reply = TenantForwardReply.model_validate(r.json())
            reply_text = reply.reply.strip()
            if not reply_text:
                raise ValueError("tenant webhook returned an empty reply")
            return reply_text
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.warning("webhook_forward_failed", error=repr(exc))
        return apology

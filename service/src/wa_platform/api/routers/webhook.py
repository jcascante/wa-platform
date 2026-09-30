import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from wa_platform.core.config import Settings, get_settings
from wa_platform.core.security import sign
from wa_platform.integrations.sqs import InboundQueue

router = APIRouter(tags=["webhook"])


@router.get("/webhook")
def verify(
    settings: Settings = Depends(get_settings),
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
):
    if mode == "subscribe" and hmac.compare_digest(token, settings.webhook_verify_token):
        return PlainTextResponse(challenge)
    raise HTTPException(403)


@router.post("/webhook")
async def webhook(request: Request, settings: Settings = Depends(get_settings)):
    """Verifies Meta's signature and enqueues for the worker Lambda, then acks within a few
    seconds (SPEC §10) — dedupe, tenant lookup, forwarding, and sending all happen off the
    request path so a slow tenant webhook or a DB hiccup never risks a Meta webhook timeout."""
    raw = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + sign(raw, settings.meta_app_secret)
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(403, "bad signature")

    payload = json.loads(raw)
    queue = InboundQueue(settings)
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            field, value = change.get("field"), change.get("value", {})
            if field == "messages":
                phone_number_id = value.get("metadata", {}).get("phone_number_id")
                for msg in value.get("messages", []):
                    queue.enqueue(phone_number_id, msg)
            elif field == "account_update":
                queue.enqueue(entry.get("id"), {"type": "account_update", "value": value})
    return {"ok": True}

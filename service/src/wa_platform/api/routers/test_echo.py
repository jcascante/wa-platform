import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from wa_platform.api.deps import get_encryptor
from wa_platform.core.security import Encryptor, verify_signature
from wa_platform.db.models import Tenant
from wa_platform.db.session import get_db

router = APIRouter(tags=["test"])


@router.post("/test/echo-webhook")
async def echo_webhook(
    request: Request,
    db: Session = Depends(get_db),
    encryptor: Encryptor = Depends(get_encryptor),
) -> dict[str, str]:
    """Stand-in tenant bot for exercising the full inbound pipeline end-to-end without a real
    tenant webhook deployed. Verifies X-Platform-Signature exactly like a real tenant would, by
    looking up that tenant's own webhook_secret — not meant to represent production tenant code."""
    raw = await request.body()
    payload = json.loads(raw)
    tenant_id = payload.get("tenant_id", "")
    tenant = db.get(Tenant, tenant_id)
    if not tenant or not tenant.webhook_secret:
        raise HTTPException(403, "unknown tenant")

    secret = await run_in_threadpool(encryptor.decrypt, tenant.webhook_secret)
    sig = request.headers.get("X-Platform-Signature", "")
    if not verify_signature(raw, secret, sig):
        raise HTTPException(403, "bad signature")

    message = payload.get("message", "")
    return {"reply": f"echo: {message}"}

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from wa_platform.api.deps import current_user_id, get_encryptor
from wa_platform.core.security import Encryptor, new_webhook_secret
from wa_platform.db.models import Tenant
from wa_platform.db.session import get_db
from wa_platform.schemas.tenant import WebhookIn, WebhookOut

router = APIRouter(prefix="/me", tags=["tenant"])


@router.post("/webhook", response_model=WebhookOut)
def set_webhook(
    body: WebhookIn,
    user_id: str = Depends(current_user_id),
    db: Session = Depends(get_db),
    encryptor: Encryptor = Depends(get_encryptor),
) -> WebhookOut:
    """Sets the URL we forward this tenant's WhatsApp chats to and issues a fresh signing
    secret so their endpoint can verify requests really came from this platform. The secret
    is returned once here in plaintext (the tenant needs it) but stored encrypted (SPEC §9)."""
    tenant = db.get(Tenant, user_id)
    if not tenant:
        raise HTTPException(404, "connect a WhatsApp number first via /onboarding/complete")
    secret = new_webhook_secret()
    tenant.webhook_url = str(body.url)
    tenant.webhook_secret = encryptor.encrypt(secret)
    db.commit()
    return WebhookOut(ok=True, webhook_url=str(body.url), webhook_secret=secret)

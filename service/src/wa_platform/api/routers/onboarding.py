from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from wa_platform.api.deps import current_user_id, get_encryptor
from wa_platform.core.config import Settings, get_settings
from wa_platform.core.security import Encryptor
from wa_platform.db.models import Tenant
from wa_platform.db.session import get_db
from wa_platform.integrations.meta.client import MetaGraphClient, MetaGraphError
from wa_platform.schemas.tenant import OnboardingIn, OnboardingOut

router = APIRouter(tags=["onboarding"])


@router.post("/onboarding/complete", response_model=OnboardingOut)
async def onboarding_complete(
    body: OnboardingIn,
    user_id: str = Depends(current_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    encryptor: Encryptor = Depends(get_encryptor),
) -> OnboardingOut:
    client = MetaGraphClient(settings)
    try:
        token = await client.exchange_code(body.code)
        await client.subscribe_app(body.waba_id, token)
        if not body.coexistence:
            await client.register_number(body.phone_number_id, token)
    except MetaGraphError as exc:
        raise HTTPException(400, f"{exc}: {exc.response.text}") from exc

    tenant = db.get(Tenant, user_id)
    encrypted_token = encryptor.encrypt(token)
    if tenant:
        tenant.waba_id = body.waba_id
        tenant.phone_number_id = body.phone_number_id
        tenant.business_token = encrypted_token
        tenant.status = "active"
    else:
        tenant = Tenant(
            tenant_id=user_id,
            waba_id=body.waba_id,
            phone_number_id=body.phone_number_id,
            business_token=encrypted_token,
            status="active",
        )
        db.add(tenant)
    db.commit()
    return OnboardingOut(ok=True, tenant_id=user_id, phone_number_id=body.phone_number_id)


@router.get("/me")
def me(user_id: str = Depends(current_user_id), db: Session = Depends(get_db)) -> dict:
    tenant = db.scalar(select(Tenant).where(Tenant.tenant_id == user_id))
    if not tenant:
        return {"tenant_id": user_id, "connected": False}
    return {
        "tenant_id": tenant.tenant_id,
        "connected": True,
        "phone_number_id": tenant.phone_number_id,
        "webhook_url": tenant.webhook_url,
        "status": tenant.status,
    }

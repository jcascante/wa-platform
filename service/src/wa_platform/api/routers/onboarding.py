import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from wa_platform.api.deps import current_user_id, get_encryptor
from wa_platform.core.config import Settings, get_settings
from wa_platform.core.logging import get_logger
from wa_platform.core.security import Encryptor
from wa_platform.db.models import Tenant
from wa_platform.db.session import get_db
from wa_platform.integrations.meta.client import MetaGraphClient, MetaGraphError
from wa_platform.schemas.tenant import OnboardingIn, OnboardingOut, TenantOut

router = APIRouter(tags=["onboarding"])
log = get_logger(__name__)


@router.post("/onboarding/complete", response_model=OnboardingOut)
async def onboarding_complete(
    body: OnboardingIn,
    user_id: str = Depends(current_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    encryptor: Encryptor = Depends(get_encryptor),
) -> OnboardingOut:
    client = MetaGraphClient(settings)
    pin = secrets.token_hex(3)
    try:
        token = await client.exchange_code(body.code)
        # The exchanged token only proves the caller went through Embedded Signup for *some*
        # WABA — without this check they could name any waba_id/phone_number_id in the request
        # body and claim a number that isn't theirs (see the tenant-isolation-reviewer note in
        # CLAUDE.md: never trust a client-supplied id for the platform's core scoping).
        owned_numbers = await client.list_phone_numbers(body.waba_id, token)
        if body.phone_number_id not in owned_numbers:
            raise HTTPException(403, "phone_number_id does not belong to this WhatsApp Business Account")
        await client.subscribe_app(body.waba_id, token)
        if not body.coexistence:
            await client.register_number(body.phone_number_id, token, pin)
    except MetaGraphError as exc:
        # Meta's raw response can contain account/token details — log it, don't hand it to the
        # client.
        log.warning("onboarding_meta_error", error=str(exc), status=exc.response.status_code)
        raise HTTPException(400, "failed to connect WhatsApp number, please try again") from exc

    encrypted_token = await run_in_threadpool(encryptor.encrypt, token)
    encrypted_pin = None if body.coexistence else await run_in_threadpool(encryptor.encrypt, pin)

    tenant = db.get(Tenant, user_id)
    if tenant:
        tenant.waba_id = body.waba_id
        tenant.phone_number_id = body.phone_number_id
        tenant.business_token = encrypted_token
        if encrypted_pin is not None:
            tenant.two_step_pin = encrypted_pin
        tenant.status = "active"
    else:
        tenant = Tenant(
            tenant_id=user_id,
            waba_id=body.waba_id,
            phone_number_id=body.phone_number_id,
            business_token=encrypted_token,
            two_step_pin=encrypted_pin,
            status="active",
        )
        db.add(tenant)
    try:
        await run_in_threadpool(db.commit)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "this phone number is already connected to another account") from exc
    return OnboardingOut(ok=True, tenant_id=user_id, phone_number_id=body.phone_number_id)


@router.get("/me", response_model=TenantOut)
def me(user_id: str = Depends(current_user_id), db: Session = Depends(get_db)) -> TenantOut:
    tenant = db.scalar(select(Tenant).where(Tenant.tenant_id == user_id))
    if not tenant:
        return TenantOut(tenant_id=user_id, connected=False)
    return TenantOut(
        tenant_id=tenant.tenant_id,
        connected=True,
        phone_number_id=tenant.phone_number_id,
        webhook_url=tenant.webhook_url,
        status=tenant.status,
    )

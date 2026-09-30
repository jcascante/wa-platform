from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from wa_platform.core.config import Settings, get_settings
from wa_platform.core.security import Encryptor
from wa_platform.db.models import User
from wa_platform.db.session import get_db


def current_user_id(
    authorization: str = Header(...),
    db: Session = Depends(get_db),
) -> str:
    """Expects 'Authorization: Bearer <api_key>'. Returns the user_id (== tenant_id)."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    api_key = authorization.removeprefix("Bearer ").strip()
    user = db.scalar(select(User).where(User.api_key == api_key))
    if not user:
        raise HTTPException(401, "invalid api key")
    return user.user_id


def get_encryptor(settings: Settings = Depends(get_settings)) -> Encryptor:
    return Encryptor(settings)

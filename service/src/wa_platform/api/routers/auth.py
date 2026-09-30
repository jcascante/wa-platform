import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from wa_platform.api.deps import current_user_id
from wa_platform.core.security import (
    DUMMY_PASSWORD_HASH,
    hash_api_key,
    hash_password,
    new_api_key,
    verify_password,
)
from wa_platform.db.models import User
from wa_platform.db.session import get_db
from wa_platform.schemas.auth import AuthOut, LoginIn, LoginOut, RegisterIn

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthOut)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> AuthOut:
    api_key = new_api_key()
    user = User(
        user_id=secrets.token_hex(8),
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        api_key_hash=hash_api_key(api_key),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "email already registered") from exc
    return AuthOut(user_id=user.user_id, api_key=api_key)


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> LoginOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    # Verify against a real hash either way (a dummy one when there's no such user) so the
    # response time doesn't reveal which emails are registered.
    password_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    if not user or not verify_password(body.password, password_hash):
        raise HTTPException(401, "invalid credentials")
    return LoginOut(user_id=user.user_id)


@router.post("/api-key/rotate", response_model=AuthOut)
def rotate_api_key(user_id: str = Depends(current_user_id), db: Session = Depends(get_db)) -> AuthOut:
    """Auths with the current key, issues a new one, and invalidates the old one immediately —
    since we only store a hash, a lost key can't be recovered, only replaced."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "user not found")
    api_key = new_api_key()
    user.api_key_hash = hash_api_key(api_key)
    db.commit()
    return AuthOut(user_id=user.user_id, api_key=api_key)

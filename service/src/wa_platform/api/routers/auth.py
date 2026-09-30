from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from wa_platform.core.security import hash_password, new_api_key, verify_password
from wa_platform.db.models import User
from wa_platform.db.session import get_db
from wa_platform.schemas.auth import AuthOut, LoginIn, RegisterIn

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthOut)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> AuthOut:
    import secrets

    user = User(
        user_id=secrets.token_hex(8),
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        api_key=new_api_key(),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "email already registered") from exc
    return AuthOut(user_id=user.user_id, api_key=user.api_key)


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> AuthOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "invalid credentials")
    return AuthOut(user_id=user.user_id, api_key=user.api_key)

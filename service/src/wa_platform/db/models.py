from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wa_platform.db.base import Base


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    api_key: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped["Tenant | None"] = relationship(back_populates="user")


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    waba_id: Mapped[str]
    phone_number_id: Mapped[str] = mapped_column(unique=True, index=True)
    # Both ciphertext (KMS-encrypted via Encryptor) — see core/security.py.
    business_token: Mapped[str]
    webhook_url: Mapped[str | None]
    webhook_secret: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="active")  # active | offboarded | suspended
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="tenant")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_tenant_wa_created", "tenant_id", "wa_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.tenant_id"))
    wa_id: Mapped[str]
    direction: Mapped[str]  # inbound | outbound
    wa_message_id: Mapped[str | None]
    body: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessedMessage(Base):
    """Dedupe guard for Meta's webhook retries — insert must happen before any side effect."""

    __tablename__ = "processed_messages"

    wa_message_id: Mapped[str] = mapped_column(primary_key=True)

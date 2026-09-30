"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("api_key", sa.String(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "tenants",
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("users.user_id"), primary_key=True),
        sa.Column("waba_id", sa.String(), nullable=False),
        sa.Column("phone_number_id", sa.String(), nullable=False, unique=True),
        sa.Column("business_token", sa.String(), nullable=False),
        sa.Column("webhook_url", sa.String(), nullable=True),
        sa.Column("webhook_secret", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tenants_phone_number_id", "tenants", ["phone_number_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("wa_id", sa.String(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("wa_message_id", sa.String(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_messages_tenant_wa_created", "messages", ["tenant_id", "wa_id", "created_at"]
    )

    op.create_table(
        "processed_messages",
        sa.Column("wa_message_id", sa.String(), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("processed_messages")
    op.drop_index("ix_messages_tenant_wa_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_tenants_phone_number_id", table_name="tenants")
    op.drop_table("tenants")
    op.drop_table("users")

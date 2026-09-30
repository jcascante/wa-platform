"""api key hash and two-step pin

Revision ID: 041d19676244
Revises: 0001
Create Date: 2026-09-30

Hand-written, not the raw autogenerate output — autogenerate also flagged unrelated pre-existing
drift in 0001 (created_at NOT NULL, messages.body column type, tenants' unique-constraint-vs-index
duplication) that isn't part of this change; left alone rather than folded in here.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "041d19676244"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("two_step_pin", sa.String(), nullable=True))

    # api_key -> api_key_hash isn't a rename: the column now holds a SHA-256 digest, not the
    # plaintext key (core/security.py hash_api_key) — no data migration is possible or wanted,
    # every existing key is invalidated and users re-register/rotate.
    op.add_column("users", sa.Column("api_key_hash", sa.String(), nullable=False))
    op.create_index(op.f("ix_users_api_key_hash"), "users", ["api_key_hash"], unique=True)
    op.drop_constraint(op.f("users_api_key_key"), "users", type_="unique")
    op.drop_column("users", "api_key")


def downgrade() -> None:
    op.add_column("users", sa.Column("api_key", sa.String(), nullable=False))
    op.create_unique_constraint(op.f("users_api_key_key"), "users", ["api_key"])
    op.drop_index(op.f("ix_users_api_key_hash"), table_name="users")
    op.drop_column("users", "api_key_hash")

    op.drop_column("tenants", "two_step_pin")

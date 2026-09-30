import pytest
from sqlalchemy import select

from wa_platform.db.models import Message, ProcessedMessage, Tenant, User
from wa_platform.workers.message_processor import handle_message


class _FakeEncryptor:
    """core.security.Encryptor talks to KMS — these tests only need a round trip."""

    def encrypt(self, plaintext: str) -> str:
        return plaintext

    def decrypt(self, ciphertext: str) -> str:
        return ciphertext


class _FakeMeta:
    def __init__(self):
        self.calls: list[tuple] = []

    async def mark_read(self, phone_number_id, token, message_id):
        self.calls.append(("mark_read", message_id))

    async def send_text(self, phone_number_id, token, to, body):
        self.calls.append(("send_text", body))


def _make_tenant(pg_db) -> Tenant:
    user = User(user_id="t1", email="t1@example.com", password_hash="x", api_key_hash="x")
    tenant = Tenant(
        tenant_id="t1",
        waba_id="waba1",
        phone_number_id="phone1",
        business_token="tok",
        status="active",
    )
    pg_db.add_all([user, tenant])
    pg_db.commit()
    return tenant


async def test_handle_message_dedupes_same_wa_message_id(pg_db):
    _make_tenant(pg_db)
    msg = {"id": "wamid.1", "from": "15551234567", "type": "text", "text": {"body": "hi"}}

    await handle_message(pg_db, None, _FakeEncryptor(), _FakeMeta(), "phone1", msg)
    await handle_message(pg_db, None, _FakeEncryptor(), _FakeMeta(), "phone1", msg)

    inbound = pg_db.scalars(select(Message).where(Message.direction == "inbound")).all()
    assert len(inbound) == 1


async def test_handle_message_removes_dedupe_row_on_failure(pg_db):
    _make_tenant(pg_db)
    # Missing "from" -> KeyError inside message handling, after the dedupe row is inserted.
    bad_msg = {"id": "wamid.2", "type": "text", "text": {"body": "hi"}}

    with pytest.raises(KeyError):
        await handle_message(pg_db, None, _FakeEncryptor(), _FakeMeta(), "phone1", bad_msg)

    # The dedupe row must not survive a failed attempt — otherwise Meta's retry of the same
    # message is silently dropped forever instead of actually being retried.
    assert pg_db.get(ProcessedMessage, "wamid.2") is None

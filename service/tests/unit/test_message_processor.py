import json

import httpx
import pytest
import respx

from wa_platform.core.security import sign
from wa_platform.db.models import Tenant
from wa_platform.workers import message_processor as mp

pytestmark = pytest.mark.usefixtures("_no_dns")


class _FakeEncryptor:
    """core.security.Encryptor talks to KMS — these tests only need a round trip, not real
    envelope encryption."""

    def encrypt(self, plaintext: str) -> str:
        return plaintext

    def decrypt(self, ciphertext: str) -> str:
        return ciphertext


@pytest.fixture
def _no_dns(monkeypatch):
    # The real resolution/rejection logic (core/ssrf_guard) has its own unit tests — keep these
    # hermetic instead of depending on DNS.
    monkeypatch.setattr(mp, "assert_public_host", lambda host: None)


def _tenant(webhook_url: str | None = "https://tenant.example.com/webhook") -> Tenant:
    return Tenant(
        tenant_id="t1",
        waba_id="waba1",
        phone_number_id="phone1",
        business_token="tok",
        webhook_url=webhook_url,
        webhook_secret="secret",
        status="active",
    )


async def test_forward_no_webhook_configured():
    tenant = _tenant(webhook_url=None)
    reply = await mp._forward_to_tenant_webhook(_FakeEncryptor(), tenant, "wa1", "hi", [], mp.log)
    assert "isn't connected" in reply


@respx.mock
async def test_forward_empty_reply_degrades_to_apology():
    respx.post("https://tenant.example.com/webhook").mock(
        return_value=httpx.Response(200, json={"reply": "   "})
    )
    reply = await mp._forward_to_tenant_webhook(_FakeEncryptor(), _tenant(), "wa1", "hi", [], mp.log)
    assert "went wrong" in reply


@respx.mock
async def test_forward_malformed_reply_degrades_to_apology():
    respx.post("https://tenant.example.com/webhook").mock(return_value=httpx.Response(200, json=["oops"]))
    reply = await mp._forward_to_tenant_webhook(_FakeEncryptor(), _tenant(), "wa1", "hi", [], mp.log)
    assert "went wrong" in reply


@respx.mock
async def test_forward_non_2xx_degrades_to_apology():
    respx.post("https://tenant.example.com/webhook").mock(return_value=httpx.Response(500))
    reply = await mp._forward_to_tenant_webhook(_FakeEncryptor(), _tenant(), "wa1", "hi", [], mp.log)
    assert "went wrong" in reply


@respx.mock
async def test_forward_network_error_degrades_to_apology():
    respx.post("https://tenant.example.com/webhook").mock(side_effect=httpx.ConnectTimeout("timed out"))
    reply = await mp._forward_to_tenant_webhook(_FakeEncryptor(), _tenant(), "wa1", "hi", [], mp.log)
    assert "went wrong" in reply


@respx.mock
async def test_forward_happy_path_strips_reply_and_signs_body():
    route = respx.post("https://tenant.example.com/webhook").mock(
        return_value=httpx.Response(200, json={"reply": " hello there "})
    )
    reply = await mp._forward_to_tenant_webhook(
        _FakeEncryptor(), _tenant(), "wa1", "hi", [{"role": "user", "content": "earlier"}], mp.log
    )
    assert reply == "hello there"

    sent_request = route.calls[0].request
    sent_body = json.loads(sent_request.content)
    assert sent_body == {
        "tenant_id": "t1",
        "from": "wa1",
        "message": "hi",
        "history": [{"role": "user", "content": "earlier"}],
    }
    assert sent_request.headers["X-Platform-Signature"] == sign(sent_request.content, "secret")


@respx.mock
async def test_forward_rejects_unsafe_host(monkeypatch):
    from wa_platform.core.ssrf_guard import UnsafeWebhookHost

    def _raise(host):
        raise UnsafeWebhookHost(f"webhook host resolves to a non-public address: {host}")

    monkeypatch.setattr(mp, "assert_public_host", _raise)
    route = respx.post("https://tenant.example.com/webhook").mock(return_value=httpx.Response(200))
    reply = await mp._forward_to_tenant_webhook(_FakeEncryptor(), _tenant(), "wa1", "hi", [], mp.log)
    assert "went wrong" in reply
    assert not route.called  # never even attempted the request

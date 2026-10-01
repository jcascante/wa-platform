import httpx
import pytest
import respx

from wa_platform.core.config import Settings
from wa_platform.integrations.meta.client import MetaGraphClient, MetaGraphError


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        meta_app_id="app-id",
        meta_app_secret="app-secret",
        webhook_verify_token="verify-token",
        kms_key_id="test-key",
        sqs_queue_url="https://sqs.us-east-1.amazonaws.com/000000000000/test",
    )


@pytest.fixture
def client(settings: Settings) -> MetaGraphClient:
    return MetaGraphClient(settings)


@respx.mock
async def test_exchange_code_returns_access_token(client: MetaGraphClient):
    route = respx.post(f"{client._base}/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "long-lived-token"})
    )
    token = await client.exchange_code("auth-code")
    assert token == "long-lived-token"
    assert route.called


@respx.mock
async def test_exchange_code_raises_on_non_200(client: MetaGraphClient):
    respx.post(f"{client._base}/oauth/access_token").mock(
        return_value=httpx.Response(400, json={"error": {"message": "invalid code"}})
    )
    with pytest.raises(MetaGraphError, match="token exchange failed"):
        await client.exchange_code("bad-code")


@respx.mock
async def test_subscribe_app_raises_on_failure(client: MetaGraphClient):
    respx.post(f"{client._base}/waba-123/subscribed_apps").mock(return_value=httpx.Response(403))
    with pytest.raises(MetaGraphError, match="subscribe failed"):
        await client.subscribe_app("waba-123", "token")


@respx.mock
async def test_register_number_sends_pin(client: MetaGraphClient):
    route = respx.post(f"{client._base}/phone-1/register").mock(return_value=httpx.Response(200))
    await client.register_number("phone-1", "token", "123456")
    assert route.called
    import json

    sent = json.loads(route.calls[0].request.content)
    assert sent["messaging_product"] == "whatsapp"
    assert sent["pin"] == "123456"


@respx.mock
async def test_list_phone_numbers_returns_ids(client: MetaGraphClient):
    respx.get(f"{client._base}/waba-123/phone_numbers").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "phone-1"}, {"id": "phone-2"}]})
    )
    ids = await client.list_phone_numbers("waba-123", "token")
    assert ids == ["phone-1", "phone-2"]


@respx.mock
async def test_list_phone_numbers_raises_on_failure(client: MetaGraphClient):
    respx.get(f"{client._base}/waba-123/phone_numbers").mock(return_value=httpx.Response(403))
    with pytest.raises(MetaGraphError, match="listing phone numbers failed"):
        await client.list_phone_numbers("waba-123", "token")


@respx.mock
async def test_send_text_truncates_to_4096_chars(client: MetaGraphClient):
    route = respx.post(f"{client._base}/phone-1/messages").mock(return_value=httpx.Response(200, json={}))
    long_body = "x" * 5000
    resp = await client.send_text("phone-1", "token", "15551234567", long_body)
    assert resp is not None and resp.status_code == 200
    payload = route.calls[0].request.content
    assert b'"x"' not in payload  # sanity: it's JSON, not a raw string dump
    import json

    sent_body = json.loads(payload)["text"]["body"]
    assert len(sent_body) == 4096


@respx.mock
async def test_send_returns_none_on_network_error(client: MetaGraphClient):
    respx.post(f"{client._base}/phone-1/messages").mock(side_effect=httpx.ConnectTimeout("timed out"))
    resp = await client.send_text("phone-1", "token", "15551234567", "hi")
    assert resp is None


@respx.mock
async def test_mark_read_posts_status(client: MetaGraphClient):
    route = respx.post(f"{client._base}/phone-1/messages").mock(return_value=httpx.Response(200, json={}))
    await client.mark_read("phone-1", "token", "wamid.abc123")
    import json

    sent = json.loads(route.calls[0].request.content)
    assert sent["status"] == "read"
    assert sent["message_id"] == "wamid.abc123"

import os

import pytest

from wa_platform.integrations.meta.client import MetaGraphClient

pytestmark = pytest.mark.live


async def test_subscribe_app_against_real_waba(live_client: MetaGraphClient):
    """Confirms our app can subscribe to the test WABA with the current token/permission set —
    this is the step most likely to break silently if a Meta permission lapses or the Graph
    API version we're pinned to (GRAPH_VERSION) changes this endpoint's shape."""
    await live_client.subscribe_app(os.environ["META_TEST_WABA_ID"], os.environ["META_TEST_ACCESS_TOKEN"])


async def test_send_text_against_real_number(live_client: MetaGraphClient):
    resp = await live_client.send_text(
        os.environ["META_TEST_PHONE_NUMBER_ID"],
        os.environ["META_TEST_ACCESS_TOKEN"],
        os.environ["META_TEST_RECIPIENT_WA_ID"],
        "wa-platform live test — safe to ignore",
    )
    assert resp is not None
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "messages" in body

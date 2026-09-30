import pytest
from pydantic import ValidationError

from wa_platform.schemas.tenant import WebhookIn


def test_webhook_url_requires_https():
    WebhookIn(url="https://example.com/chat")
    with pytest.raises(ValidationError):
        WebhookIn(url="http://example.com/chat")

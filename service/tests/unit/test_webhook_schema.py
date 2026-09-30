import pytest
from pydantic import ValidationError

from wa_platform.schemas.tenant import WebhookIn

# IP literals, not real hostnames — keeps this test hermetic (no DNS lookup) since the validator
# now also runs an SSRF check (core/ssrf_guard) on top of the https-only check.
PUBLIC_URL = "https://8.8.8.8/chat"
PRIVATE_URL = "https://10.42.0.5/chat"


def test_webhook_url_requires_https():
    WebhookIn(url=PUBLIC_URL)
    with pytest.raises(ValidationError):
        WebhookIn(url="http://8.8.8.8/chat")


def test_webhook_url_rejects_private_ip():
    with pytest.raises(ValidationError, match="non-public"):
        WebhookIn(url=PRIVATE_URL)

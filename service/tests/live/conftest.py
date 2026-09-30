import os

import pytest

from wa_platform.core.config import Settings
from wa_platform.integrations.meta.client import MetaGraphClient

REQUIRED_ENV = [
    "META_TEST_APP_ID",
    "META_TEST_APP_SECRET",
    "META_TEST_ACCESS_TOKEN",
    "META_TEST_WABA_ID",
    "META_TEST_PHONE_NUMBER_ID",
    "META_TEST_RECIPIENT_WA_ID",
]


@pytest.fixture(autouse=True)
def _require_live_credentials():
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        pytest.skip(f"missing live Meta test credentials: {', '.join(missing)} — see tests/live/README.md")


@pytest.fixture
def live_client() -> MetaGraphClient:
    settings = Settings(
        database_url="sqlite:///:memory:",  # unused by MetaGraphClient, Settings just needs a value
        meta_app_id=os.environ["META_TEST_APP_ID"],
        meta_app_secret=os.environ["META_TEST_APP_SECRET"],
        webhook_verify_token="unused",
        kms_key_id="unused",
        sqs_queue_url="https://sqs.us-east-1.amazonaws.com/000000000000/unused",
    )
    return MetaGraphClient(settings)

import pytest

from wa_platform.core.ssrf_guard import UnsafeWebhookHost, assert_public_host

# All IP literals — resolving these is a local parse, not a real DNS query, so these tests stay
# fast and hermetic.


def test_rejects_private_ip():
    with pytest.raises(UnsafeWebhookHost):
        assert_public_host("10.42.0.5")


def test_rejects_loopback():
    with pytest.raises(UnsafeWebhookHost):
        assert_public_host("127.0.0.1")


def test_rejects_link_local():
    assert_public_host("8.8.8.8")  # sanity: doesn't raise for a public address
    with pytest.raises(UnsafeWebhookHost):
        assert_public_host("169.254.169.254")  # cloud instance metadata endpoint


def test_allows_public_ip():
    assert_public_host("8.8.8.8")


def test_raises_on_unresolvable_host():
    with pytest.raises(UnsafeWebhookHost):
        assert_public_host("this-host-does-not-exist.invalid")

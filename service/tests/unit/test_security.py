from wa_platform.core.security import (
    DUMMY_PASSWORD_HASH,
    hash_api_key,
    hash_password,
    new_api_key,
    sign,
    verify_password,
    verify_signature,
)


def test_password_roundtrip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong password", h)


def test_dummy_password_hash_never_verifies():
    # Used to equalize login timing for an unknown email — must never accidentally match a real
    # password.
    assert not verify_password("anything", DUMMY_PASSWORD_HASH)


def test_hash_api_key_is_deterministic_and_distinct():
    key = new_api_key()
    assert hash_api_key(key) == hash_api_key(key)
    assert hash_api_key(key) != key
    assert hash_api_key(key) != hash_api_key(new_api_key())


def test_signature_roundtrip():
    secret = "shh"
    body = b'{"hello":"world"}'
    sig = sign(body, secret)
    assert verify_signature(body, secret, sig)
    assert not verify_signature(body, "other-secret", sig)
    assert not verify_signature(b"tampered", secret, sig)

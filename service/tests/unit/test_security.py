from wa_platform.core.security import hash_password, sign, verify_password, verify_signature


def test_password_roundtrip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong password", h)


def test_signature_roundtrip():
    secret = "shh"
    body = b'{"hello":"world"}'
    sig = sign(body, secret)
    assert verify_signature(body, secret, sig)
    assert not verify_signature(body, "other-secret", sig)
    assert not verify_signature(b"tampered", secret, sig)

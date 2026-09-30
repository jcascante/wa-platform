import base64
import hashlib
import hmac
import secrets

import boto3
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from wa_platform.core.config import Settings

_hasher = PasswordHasher()

# Computed once so an unknown-email login still pays the same argon2 cost as a real one —
# without this, the "no such user" branch returns before hashing anything and the response
# time itself tells an attacker which emails are registered.
DUMMY_PASSWORD_HASH = PasswordHasher().hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def new_api_key() -> str:
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    """Lookup/verification hash for API keys, stored in place of the plaintext (users.api_key_hash).
    Unlike passwords, a 256-bit random token doesn't need a slow salted hash to resist brute force —
    a fast digest keeps auth cheap on every request, and equality-lookup by hash is safe at this
    entropy."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def new_webhook_secret() -> str:
    return secrets.token_urlsafe(24)


def sign(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def verify_signature(payload: bytes, secret: str, signature: str) -> bool:
    return hmac.compare_digest(sign(payload, secret), signature)


class Encryptor:
    """Encrypts tenant secrets (business_token, webhook_secret) at rest via KMS, per SPEC §9 —
    the prototype stored these in plaintext and must not go to prod. Ciphertext is stored as
    base64 text so the column type doesn't change between dev (LocalStack) and prod (real KMS)."""

    def __init__(self, settings: Settings):
        self._key_id = settings.kms_key_id
        self._client = boto3.client(
            "kms",
            region_name=settings.aws_region,
            endpoint_url=settings.aws_endpoint_url,
        )

    def encrypt(self, plaintext: str) -> str:
        resp = self._client.encrypt(KeyId=self._key_id, Plaintext=plaintext.encode())
        return base64.b64encode(resp["CiphertextBlob"]).decode()

    def decrypt(self, ciphertext: str) -> str:
        blob = base64.b64decode(ciphertext)
        resp = self._client.decrypt(KeyId=self._key_id, CiphertextBlob=blob)
        return resp["Plaintext"].decode()

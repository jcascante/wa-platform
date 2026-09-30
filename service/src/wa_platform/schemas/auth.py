from pydantic import BaseModel, EmailStr, field_validator


class RegisterIn(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class AuthOut(BaseModel):
    """Returned by /auth/register and /auth/api-key/rotate — the only two moments the plaintext
    key is available. We store a hash (users.api_key_hash), not the key itself, so it can't be
    shown again after this."""

    user_id: str
    api_key: str


class LoginOut(BaseModel):
    user_id: str

from pydantic import BaseModel, HttpUrl, field_validator

from wa_platform.core.ssrf_guard import UnsafeWebhookHost, assert_public_host


class OnboardingIn(BaseModel):
    code: str
    waba_id: str
    phone_number_id: str
    coexistence: bool = False
    # Must match the URL of the page that called FB.login, or Meta's code exchange fails with
    # OAuthException 36008 — the JS SDK ties the code to that page as its implicit redirect_uri.
    redirect_uri: str = ""


class OnboardingOut(BaseModel):
    ok: bool
    tenant_id: str
    phone_number_id: str


class TenantOut(BaseModel):
    tenant_id: str
    connected: bool
    phone_number_id: str | None = None
    webhook_url: str | None = None
    status: str | None = None


class WebhookIn(BaseModel):
    url: HttpUrl

    @field_validator("url")
    @classmethod
    def require_https(cls, v: HttpUrl) -> HttpUrl:
        # SPEC §9: tenant webhook_url was unvalidated in the prototype — enforce https here.
        if v.scheme != "https":
            raise ValueError("webhook url must use https")
        if v.host is None:
            raise ValueError("webhook url must have a host")
        # Catches the obvious SSRF case at set-time; the check that actually matters runs again
        # right before every forward (workers/message_processor.py) since DNS can change later.
        try:
            assert_public_host(v.host)
        except UnsafeWebhookHost as exc:
            raise ValueError(str(exc)) from exc
        return v


class WebhookOut(BaseModel):
    ok: bool
    webhook_url: str
    webhook_secret: str

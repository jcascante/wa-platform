from pydantic import BaseModel, HttpUrl, field_validator


class OnboardingIn(BaseModel):
    code: str
    waba_id: str
    phone_number_id: str
    coexistence: bool = False


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
        return v


class WebhookOut(BaseModel):
    ok: bool
    webhook_url: str
    webhook_secret: str

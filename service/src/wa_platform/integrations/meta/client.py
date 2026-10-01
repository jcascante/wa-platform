import httpx

from wa_platform.core.config import Settings
from wa_platform.core.logging import get_logger

log = get_logger(__name__)

# Free-form replies only work within 24h of the WhatsApp user's last message (SPEC: "24-hour
# customer service window"); outside it Meta rejects the send with this code and a template is
# required instead. Not implemented yet — logging it here at least makes the failure visible.
OUTSIDE_SERVICE_WINDOW_ERROR_CODE = 131047


class MetaGraphError(Exception):
    def __init__(self, message: str, response: httpx.Response):
        super().__init__(message)
        self.response = response


class MetaGraphClient:
    """Thin wrapper over the WhatsApp Cloud API / Graph API calls the platform makes on the
    tenant's behalf (Embedded Signup exchange, subscribe, send, mark-read)."""

    def __init__(self, settings: Settings, token: str | None = None):
        self._base = settings.graph_api_base
        self._app_id = settings.meta_app_id
        self._app_secret = settings.meta_app_secret
        self._token = token

    async def exchange_code(self, code: str, redirect_uri: str = "") -> str:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"{self._base}/oauth/access_token",
                # Meta's own Embedded Signup Helper generates a POST + JSON body with an
                # explicit grant_type for this exchange, not the GET-with-query-params form the
                # legacy curl examples show — omitting grant_type here reproduced OAuthException
                # 36008 regardless of what redirect_uri was sent.
                json={
                    "client_id": self._app_id,
                    "client_secret": self._app_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        if r.status_code != 200:
            raise MetaGraphError("token exchange failed", r)
        return r.json()["access_token"]

    async def subscribe_app(self, waba_id: str, token: str) -> None:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"{self._base}/{waba_id}/subscribed_apps",
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code != 200:
            raise MetaGraphError("subscribe failed", r)

    async def list_phone_numbers(self, waba_id: str, token: str) -> list[str]:
        """IDs of the phone numbers actually associated with this WABA, per the exchanged token.
        Used to stop onboarding from accepting a phone_number_id the caller doesn't own — Meta's
        own subscribe/register calls don't fail just because the caller supplied someone else's
        ID (see api/routers/onboarding.py)."""
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                f"{self._base}/{waba_id}/phone_numbers",
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code != 200:
            raise MetaGraphError("listing phone numbers failed", r)
        return [item["id"] for item in r.json().get("data", [])]

    async def register_number(self, phone_number_id: str, token: str, pin: str) -> None:
        """`pin` sets the number's two-step-verification PIN. The caller persists it (encrypted)
        since Meta never hands it back — it's needed again to re-register or migrate the number
        later."""
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"{self._base}/{phone_number_id}/register",
                headers={"Authorization": f"Bearer {token}"},
                json={"messaging_product": "whatsapp", "pin": pin},
            )
        if r.status_code != 200:
            raise MetaGraphError("register failed", r)

    async def send(self, phone_number_id: str, token: str, payload: dict) -> httpx.Response | None:
        """Never raises — a network blip or Meta-side error here must not take down message
        processing (SPEC §9); caller logs and moves on. Logs the failure itself either way, since
        nothing else would otherwise surface it (e.g. a reply sent outside the 24h service
        window, Meta error code 131047)."""
        try:
            # Short timeout — this runs twice per inbound message (mark_read, send_text) inside
            # the worker Lambda's budget alongside the tenant webhook's own 30s (SPEC §6). See
            # infra/terraform/modules/lambda_worker for how the function timeout adds these up.
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    f"{self._base}/{phone_number_id}/messages",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"messaging_product": "whatsapp", **payload},
                )
        except httpx.HTTPError as exc:
            log.warning("meta_send_network_error", error=repr(exc))
            return None

        if r.status_code != 200:
            error_code = None
            try:
                error_code = r.json().get("error", {}).get("code")
            except ValueError:
                pass
            if error_code == OUTSIDE_SERVICE_WINDOW_ERROR_CODE:
                log.warning("meta_send_outside_service_window", phone_number_id=phone_number_id)
            else:
                log.warning("meta_send_failed", status=r.status_code, body=r.text[:500])
        return r

    async def send_text(self, phone_number_id: str, token: str, to: str, body: str):
        return await self.send(
            phone_number_id, token, {"to": to, "type": "text", "text": {"body": body[:4096]}}
        )

    async def mark_read(self, phone_number_id: str, token: str, message_id: str):
        return await self.send(phone_number_id, token, {"status": "read", "message_id": message_id})

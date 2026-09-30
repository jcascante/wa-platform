import secrets

import httpx

from wa_platform.core.config import Settings


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

    async def exchange_code(self, code: str) -> str:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                f"{self._base}/oauth/access_token",
                params={"client_id": self._app_id, "client_secret": self._app_secret, "code": code},
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

    async def register_number(self, phone_number_id: str, token: str) -> None:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"{self._base}/{phone_number_id}/register",
                headers={"Authorization": f"Bearer {token}"},
                json={"messaging_product": "whatsapp", "pin": secrets.token_hex(3)},
            )
        if r.status_code != 200:
            raise MetaGraphError("register failed", r)

    async def send(self, phone_number_id: str, token: str, payload: dict) -> httpx.Response | None:
        """Never raises — a network blip or Meta-side error here must not take down message
        processing (SPEC §9); caller logs and moves on."""
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                return await client.post(
                    f"{self._base}/{phone_number_id}/messages",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"messaging_product": "whatsapp", **payload},
                )
        except httpx.HTTPError:
            return None

    async def send_text(self, phone_number_id: str, token: str, to: str, body: str):
        return await self.send(
            phone_number_id, token, {"to": to, "type": "text", "text": {"body": body[:4096]}}
        )

    async def mark_read(self, phone_number_id: str, token: str, message_id: str):
        return await self.send(phone_number_id, token, {"status": "read", "message_id": message_id})

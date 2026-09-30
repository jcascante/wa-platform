from typing import Any

from pydantic import BaseModel


class TenantForwardPayload(BaseModel):
    """What we POST to a tenant's own webhook_url (SPEC §6 contract)."""

    tenant_id: str
    from_: str
    message: str
    history: list[dict[str, str]]

    def to_wire(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "from": self.from_,
            "message": self.message,
            "history": self.history,
        }


class TenantForwardReply(BaseModel):
    reply: str = ""

from fastapi import FastAPI

from wa_platform.api.routers import auth, me, onboarding, webhook
from wa_platform.core.logging import configure_logging

configure_logging()

app = FastAPI(title="WhatsApp AI Platform")
app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(me.router)
app.include_router(webhook.router)

import os

from fastapi import FastAPI

from wa_platform.api.routers import auth, dev_tools, me, onboarding, test_echo, webhook
from wa_platform.core.logging import configure_logging

configure_logging()

app = FastAPI(title="WhatsApp AI Platform")
app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(me.router)
app.include_router(webhook.router)
app.include_router(test_echo.router)

# Environment check avoids pulling in Settings (and its Secrets Manager hydration) at import
# time — this only ever needs to gate out of prod, never read real config.
if os.environ.get("ENVIRONMENT", "dev") != "prod":
    app.include_router(dev_tools.router)

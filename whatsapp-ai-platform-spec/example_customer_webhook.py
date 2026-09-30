"""
Example of what a *user's own* webhook receiver looks like on their side.
This is NOT part of the platform — it's what a platform user would build/host
themselves and paste into /me/webhook as their `url`.

It verifies the X-Platform-Signature header using the webhook_secret they got
back from POST /me/webhook, then replies with a simple echo (swap in their own AI).

Run:  WEBHOOK_SECRET=... uvicorn example_customer_webhook:app --port 9000
"""
import hashlib
import hmac
import os

from fastapi import FastAPI, HTTPException, Request

SECRET = os.environ["WEBHOOK_SECRET"]
app = FastAPI()


@app.post("/chat")
async def chat(request: Request):
    raw = await request.body()
    sig = request.headers.get("X-Platform-Signature", "")
    expected = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(403, "bad signature")

    body = await request.json()
    text = body["message"]
    # --- replace this with a real AI call, scoped to this tenant's business ---
    reply = f"You said: {text}"
    return {"reply": reply}

"""
Multi-tenant WhatsApp Cloud API platform (Tech Provider / Embedded Signup model).

Use case: your own users register on this platform, connect their WhatsApp Business
number via Embedded Signup, and configure a webhook URL. Every inbound WhatsApp message
for their number is forwarded (signed) to that URL, and whatever it returns is sent back
to the WhatsApp user.

High-level flow:
  1. POST /auth/register -> user gets an api_key. POST /auth/login to fetch it again.
  2. Authenticated user runs Embedded Signup in the browser, then calls
     POST /onboarding/complete with {code, waba_id, phone_number_id}.
     We exchange the code for a business token, subscribe our app to their WABA,
     register the number, and store it as *their* tenant (max one per user for now).
  3. User sets their webhook: POST /me/webhook {url, secret?}.
  4. Meta POSTs every WhatsApp event to /webhook (single shared endpoint for all tenants).
     We verify Meta's signature, dedupe, find the owning tenant by phone_number_id,
     and forward the message to that tenant's webhook URL (signed with their secret).
     Their webhook responds with {"reply": "..."} and we send it back over WhatsApp.

Run:  uvicorn main:app --reload --port 8000
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import closing

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, HttpUrl

GRAPH = f"https://graph.facebook.com/{os.environ.get('GRAPH_VERSION', 'v23.0')}"  # pin to a current version
APP_ID = os.environ["META_APP_ID"]
APP_SECRET = os.environ["META_APP_SECRET"]
VERIFY_TOKEN = os.environ["WEBHOOK_VERIFY_TOKEN"]
DB_PATH = os.environ.get("DB_PATH", "wa.db")

app = FastAPI(title="WhatsApp AI Platform")


# ---------------------------------------------------------------- storage (swap for Postgres in prod)
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(db()) as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                api_key TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS tenants (
                tenant_id TEXT PRIMARY KEY,          -- = user_id (one WA number per user, for now)
                waba_id TEXT NOT NULL,
                phone_number_id TEXT NOT NULL UNIQUE,
                business_token TEXT NOT NULL,        -- ENCRYPT AT REST in production (KMS / Fernet)
                webhook_url TEXT,                    -- where WE forward inbound chats to
                webhook_secret TEXT,                 -- used to sign that forward, so their side can verify us
                status TEXT NOT NULL DEFAULT 'active',
                FOREIGN KEY (tenant_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS processed (message_id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT, wa_id TEXT, role TEXT, content TEXT
            );
            """
        )
        c.commit()


init_db()


# ---------------------------------------------------------------- auth (simple API-key model)
def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()  # placeholder — use bcrypt/argon2 in production


class RegisterIn(BaseModel):
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


@app.post("/auth/register")
def register(body: RegisterIn):
    user_id = secrets.token_hex(8)
    api_key = secrets.token_urlsafe(32)
    with closing(db()) as c:
        try:
            c.execute(
                "INSERT INTO users (user_id, email, password_hash, api_key) VALUES (?,?,?,?)",
                (user_id, body.email.lower(), hash_pw(body.password), api_key),
            )
            c.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(409, "email already registered")
    return {"user_id": user_id, "api_key": api_key}


@app.post("/auth/login")
def login(body: LoginIn):
    with closing(db()) as c:
        row = c.execute(
            "SELECT user_id, api_key FROM users WHERE email=? AND password_hash=?",
            (body.email.lower(), hash_pw(body.password)),
        ).fetchone()
    if not row:
        raise HTTPException(401, "invalid credentials")
    return {"user_id": row["user_id"], "api_key": row["api_key"]}


def current_user(authorization: str = Header(...)) -> str:
    """Expects 'Authorization: Bearer <api_key>'. Returns the user_id (== tenant_id)."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    api_key = authorization.removeprefix("Bearer ").strip()
    with closing(db()) as c:
        row = c.execute("SELECT user_id FROM users WHERE api_key=?", (api_key,)).fetchone()
    if not row:
        raise HTTPException(401, "invalid api key")
    return row["user_id"]


# ---------------------------------------------------------------- onboarding (Embedded Signup)
class OnboardingIn(BaseModel):
    code: str               # from FB.login response
    waba_id: str             # from the WA_EMBEDDED_SIGNUP FINISH message event
    phone_number_id: str     # same
    coexistence: bool = False  # True if they onboarded an existing WhatsApp Business app number


@app.post("/onboarding/complete")
async def onboarding_complete(body: OnboardingIn, user_id: str = Depends(current_user)):
    async with httpx.AsyncClient(timeout=20) as client:
        # 1) code -> business token
        r = await client.get(
            f"{GRAPH}/oauth/access_token",
            params={"client_id": APP_ID, "client_secret": APP_SECRET, "code": body.code},
        )
        if r.status_code != 200:
            raise HTTPException(400, f"token exchange failed: {r.text}")
        token = r.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        # 2) subscribe our app to this customer's WABA so webhooks flow to us
        r = await client.post(f"{GRAPH}/{body.waba_id}/subscribed_apps", headers=auth)
        if r.status_code != 200:
            raise HTTPException(400, f"subscribe failed: {r.text}")

        # 3) register the number for Cloud API (skip for coexistence)
        if not body.coexistence:
            r = await client.post(
                f"{GRAPH}/{body.phone_number_id}/register",
                headers=auth,
                json={"messaging_product": "whatsapp", "pin": secrets.token_hex(3)},
            )
            if r.status_code != 200:
                raise HTTPException(400, f"register failed: {r.text}")

    with closing(db()) as c:
        c.execute(
            "INSERT OR REPLACE INTO tenants "
            "(tenant_id, waba_id, phone_number_id, business_token, webhook_url, webhook_secret, status) "
            "VALUES (?, ?, ?, ?, "
            "  COALESCE((SELECT webhook_url FROM tenants WHERE tenant_id=?), NULL),"
            "  COALESCE((SELECT webhook_secret FROM tenants WHERE tenant_id=?), NULL),"
            "  'active')",
            (user_id, body.waba_id, body.phone_number_id, token, user_id, user_id),
        )
        c.commit()
    return {"ok": True, "tenant_id": user_id, "phone_number_id": body.phone_number_id}


# ---------------------------------------------------------------- user's own tenant config
class WebhookIn(BaseModel):
    url: HttpUrl


@app.get("/me")
def me(user_id: str = Depends(current_user)):
    with closing(db()) as c:
        row = c.execute("SELECT * FROM tenants WHERE tenant_id=?", (user_id,)).fetchone()
    if not row:
        return {"tenant_id": user_id, "connected": False}
    d = dict(row)
    d.pop("business_token", None)
    d.pop("webhook_secret", None)
    d["connected"] = True
    return d


@app.post("/me/webhook")
def set_webhook(body: WebhookIn, user_id: str = Depends(current_user)):
    """User sets the URL we forward their WhatsApp chats to. We generate a signing secret
    for them so their endpoint can verify requests really came from this platform."""
    secret = secrets.token_urlsafe(24)
    with closing(db()) as c:
        cur = c.execute(
            "UPDATE tenants SET webhook_url=?, webhook_secret=? WHERE tenant_id=?",
            (str(body.url), secret, user_id),
        )
        c.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "connect a WhatsApp number first via /onboarding/complete")
    return {"ok": True, "webhook_url": str(body.url), "webhook_secret": secret}


# ---------------------------------------------------------------- Meta webhook (shared across all tenants)
@app.get("/webhook")
def verify(
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
):
    if mode == "subscribe" and hmac.compare_digest(token, VERIFY_TOKEN):
        return PlainTextResponse(challenge)
    raise HTTPException(403)


@app.post("/webhook")
async def webhook(request: Request, bg: BackgroundTasks):
    raw = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(403, "bad signature")

    payload = json.loads(raw)
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            field, value = change.get("field"), change.get("value", {})
            if field == "messages":
                phone_number_id = value.get("metadata", {}).get("phone_number_id")
                for msg in value.get("messages", []):
                    bg.add_task(handle_message, phone_number_id, msg)
            elif field == "account_update":
                handle_account_update(entry.get("id"), value)
    return {"ok": True}  # ack fast; real work runs after the response (use a real queue in prod)


def handle_account_update(waba_id: str, value: dict):
    event = value.get("event")
    status = {"ACCOUNT_OFFBOARDED": "offboarded", "ACCOUNT_RECONNECTED": "active"}.get(event)
    if status:
        with closing(db()) as c:
            c.execute("UPDATE tenants SET status=? WHERE waba_id=?", (status, waba_id))
            c.commit()


# ---------------------------------------------------------------- message handling
async def handle_message(phone_number_id: str, msg: dict):
    # dedupe: Meta retries deliveries
    with closing(db()) as c:
        cur = c.execute("INSERT OR IGNORE INTO processed VALUES (?)", (msg["id"],))
        c.commit()
        if cur.rowcount == 0:
            return
        tenant = c.execute("SELECT * FROM tenants WHERE phone_number_id=?", (phone_number_id,)).fetchone()
    if not tenant or tenant["status"] != "active":
        return

    wa_id = msg["from"]
    await mark_read(tenant, msg["id"])

    if msg.get("type") != "text":
        await send_text(tenant, wa_id, "Sorry, I can only read text messages for now.")
        return

    text = msg["text"]["body"]
    add_history(tenant["tenant_id"], wa_id, "user", text)
    reply = await forward_to_tenant_webhook(tenant, wa_id, text)
    add_history(tenant["tenant_id"], wa_id, "assistant", reply)
    await send_text(tenant, wa_id, reply)


def add_history(tenant_id, wa_id, role, content):
    with closing(db()) as c:
        c.execute("INSERT INTO history (tenant_id, wa_id, role, content) VALUES (?,?,?,?)",
                  (tenant_id, wa_id, role, content))
        c.commit()


def get_history(tenant_id, wa_id, limit=20):
    with closing(db()) as c:
        rows = c.execute(
            "SELECT role, content FROM history WHERE tenant_id=? AND wa_id=? ORDER BY id DESC LIMIT ?",
            (tenant_id, wa_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


async def forward_to_tenant_webhook(tenant, wa_id: str, text: str) -> str:
    """Forward the inbound WhatsApp message to the tenant's own webhook, signed so they
    can verify it came from us. Their endpoint should respond with JSON: {"reply": "..."}."""
    if not tenant["webhook_url"]:
        return "This number isn't connected to a chatbot yet."

    body = json.dumps({
        "tenant_id": tenant["tenant_id"],
        "from": wa_id,
        "message": text,
        "history": get_history(tenant["tenant_id"], wa_id),
    }).encode()
    sig = hmac.new(tenant["webhook_secret"].encode(), body, hashlib.sha256).hexdigest()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                tenant["webhook_url"],
                content=body,
                headers={"Content-Type": "application/json", "X-Platform-Signature": sig},
            )
            r.raise_for_status()
            return r.json().get("reply", "")
    except (httpx.HTTPError, ValueError, KeyError) as e:
        # network failure, non-2xx from raise_for_status(), or a malformed/missing "reply" field
        print("webhook forward failed", tenant["tenant_id"], repr(e))  # use real logging in prod
        return "Sorry, something went wrong on our end. Please try again shortly."


# ---------------------------------------------------------------- Cloud API helpers (per-tenant token)
async def _post(tenant, payload):
    """POST to the Cloud API. Never raises — a network blip or Meta-side error here must not
    take down message processing; we log and move on."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"{GRAPH}/{tenant['phone_number_id']}/messages",
                headers={"Authorization": f"Bearer {tenant['business_token']}"},
                json={"messaging_product": "whatsapp", **payload},
            )
            if r.status_code >= 400:
                print("send failed", tenant["tenant_id"], r.status_code, r.text)  # use real logging/alerts
            return r
    except httpx.HTTPError as e:
        print("send errored", tenant["tenant_id"], repr(e))  # use real logging/alerts in prod
        return None


async def send_text(tenant, to: str, body: str):
    # WhatsApp text limit is 4096 chars; free-form only works inside the 24h window
    return await _post(tenant, {"to": to, "type": "text", "text": {"body": body[:4096]}})


async def mark_read(tenant, message_id: str):
    return await _post(tenant, {"status": "read", "message_id": message_id})

# WhatsApp AI Chatbot Platform — Project Spec

## 1. What this is

A multi-tenant platform where **end users (our customers) register an account, connect
their own WhatsApp Business number, and point it at their own AI chatbot via a webhook.**

We are a **Meta Tech Provider**. Customers never touch the Meta Developer Console — they
connect through an Embedded Signup popup hosted inside our product. We own one Meta app;
every customer's WhatsApp Business Account (WABA) and phone number live under our app,
and our backend proxies messages between WhatsApp and each customer's own webhook.

```
WhatsApp user <-> Meta Cloud API <-> OUR BACKEND <-> customer's webhook (their AI bot)
                                          |
                                     Postgres (users, tenants, message history)
```

## 2. Actors

- **Platform user** — a business that signs up on our platform, connects a WhatsApp
  number, and configures a webhook URL where we forward their chats.
- **WhatsApp end user** — the platform user's own customer, chatting on WhatsApp.
- **Us (the platform)** — the Meta Tech Provider. One Meta app, one set of credentials,
  many tenants underneath it.

## 3. Core user flow

1. User registers on our platform (email + password) → gets an API key / session.
2. User clicks "Connect WhatsApp" → Embedded Signup popup (Meta-hosted, inside our UI)
   → user logs in with Facebook, authorizes our app, selects/creates a WABA, verifies
   their number.
3. Popup returns `{code, waba_id, phone_number_id}` to our frontend.
4. Frontend calls our backend: `POST /onboarding/complete` with those values.
5. Backend exchanges `code` for a long-lived business token, subscribes our app to the
   customer's WABA, registers the number for Cloud API, stores everything as *their*
   tenant record.
6. User sets their webhook: `POST /me/webhook {url}` → we return a signing secret.
7. From then on: any WhatsApp message to that number arrives at our single shared
   `/webhook` endpoint (from Meta) → we identify the tenant by `phone_number_id` →
   forward the message (HMAC-signed with their secret) to *their* webhook URL →
   their webhook returns `{"reply": "..."}` → we send that back over WhatsApp.

## 4. Non-goals (v1)

- No group messaging, no media messages (images/audio/docs) beyond a graceful fallback.
- No built-in AI — we are a *routing/orchestration* platform. The tenant's own webhook
  is the "brain." (We may add an optional hosted-AI tier later.)
- No multi-number-per-user support yet — one WhatsApp number per platform account.
- No billing/metering in v1 — flag as a fast-follow (see §11).

## 5. Data model

```sql
users (
  user_id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  api_key TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
)

tenants (
  tenant_id TEXT PRIMARY KEY REFERENCES users(user_id),
  waba_id TEXT NOT NULL,
  phone_number_id TEXT UNIQUE NOT NULL,
  business_token TEXT NOT NULL,      -- ENCRYPTED at rest
  webhook_url TEXT,
  webhook_secret TEXT,               -- ENCRYPTED at rest
  status TEXT NOT NULL DEFAULT 'active',  -- active | offboarded | suspended
  created_at TIMESTAMPTZ DEFAULT now()
)

messages (                            -- renamed/expanded from the "history" prototype table
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT REFERENCES tenants(tenant_id),
  wa_id TEXT NOT NULL,                -- end user's WhatsApp ID (phone number)
  direction TEXT NOT NULL,            -- inbound | outbound
  wa_message_id TEXT,                 -- Meta's message id, for dedupe
  body TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
)

processed_messages (                  -- dedupe guard for Meta's webhook retries
  wa_message_id TEXT PRIMARY KEY
)
```

Indexes: `tenants(phone_number_id)` (lookup on every inbound webhook), `messages(tenant_id, wa_id, created_at)` (conversation history reads).

## 6. API surface (backend we own)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/register` | none | create platform account |
| POST | `/auth/login` | none | fetch API key |
| POST | `/onboarding/complete` | Bearer | finish Embedded Signup, create tenant |
| GET | `/me` | Bearer | tenant connection status |
| POST | `/me/webhook` | Bearer | set/rotate the customer's webhook URL + get signing secret |
| GET | `/webhook` | Meta verify token | Meta's webhook handshake |
| POST | `/webhook` | Meta app-secret signature | inbound WhatsApp events (all tenants, shared) |

### Contract with the tenant's own webhook (outbound from us)

We `POST` to `tenant.webhook_url`:

```json
{
  "tenant_id": "...",
  "from": "<whatsapp wa_id>",
  "message": "<text body>",
  "history": [{"role": "user|assistant", "content": "..."}]
}
```
Header: `X-Platform-Signature: <hex hmac-sha256 of raw body, keyed by webhook_secret>`

Expected response: `200 { "reply": "<text to send back>" }`. Non-2xx or timeout (30s) →
we send a generic apology message to the WhatsApp user and log the failure.

## 7. Meta / Tech Provider setup checklist

- [ ] Business Portfolio created, business verification submitted
- [ ] Meta app created with **Connect with customers through WhatsApp** use case
- [ ] Tech Provider enrollment started
- [ ] Facebook Login for Business → Embedded Signup configuration created → `config_id`
- [ ] Webhook callback URL + verify token configured; subscribed fields:
      `messages`, `account_update`, `account_alerts`, `account_review_update`
- [ ] System user created in the business portfolio; token generated with
      `whatsapp_business_messaging` + `whatsapp_business_management` for our own testing
- [ ] Test WABA + test number obtained from **API Setup** for local development
- [ ] App Review submitted (once verification clears) for the permissions above
- [ ] Payment method attached to the business portfolio

Reference docs: `developers.facebook.com/documentation/business-messaging/whatsapp/`
(embedded-signup, get-started, webhooks sections).

## 8. Compliance constraints (must design around)

- **Meta's general-purpose AI chatbot ban** (in force since Jan 15, 2026 for all
  accounts): each tenant's bot must be scoped to their own business — structured,
  task-oriented use cases (support, bookings, order tracking, FAQs), not an open-domain
  assistant. We should document this requirement for our platform users and consider
  a lightweight review/attestation step at onboarding.
- **24-hour customer service window**: free-form replies only work within 24h of the
  user's last message; outside it, a pre-approved template is required. v1 can send a
  generic "session expired" message when a send fails for this reason (error code
  131047) — template support is a fast-follow.
- **Pricing**: service messages are billed after a free monthly allowance per number
  (Meta's Oct 2026 pricing change) — verify current rates before launch and decide
  whether/how to pass costs to platform users.

## 9. Security requirements

- Verify `X-Hub-Signature-256` on every inbound `/webhook` call (already prototyped).
- Encrypt `business_token` and `webhook_secret` at rest (KMS-backed or Fernet with a
  rotated key) — the SQLite prototype stores these in plaintext and must not go to prod.
- Enforce `https://` on tenant-provided `webhook_url` (currently unvalidated).
- Real password hashing (argon2 or bcrypt) — prototype uses raw sha256.
- Rate-limit `/auth/*` and `/onboarding/complete`.
- Dedupe inbound messages on `wa_message_id` before processing (already prototyped).
- All outbound calls to Meta and to tenant webhooks must catch network-level errors,
  not just non-2xx status — a transient failure must never crash message processing.

## 10. Non-functional requirements

- Webhook handler must **ack Meta within a few seconds**: verify signature, enqueue,
  return 200 immediately; do the real work (dedupe, tenant lookup, forwarding, sending)
  in a background worker/queue (Celery/RQ/SQS — not in-process `BackgroundTasks` in prod).
- Single shared `/webhook` endpoint routes to the correct tenant by `phone_number_id` —
  never assume one tenant per deployment.
- Structured logging with tenant_id on every log line; alert on repeated webhook forward
  failures per tenant.
- Postgres in production (SQLite is prototype-only).

## 11. Suggested build order / milestones

1. **Foundation**: Postgres schema, auth (register/login with real password hashing),
   `/me`, `/me/webhook`.
2. **Meta integration**: `/onboarding/complete` against the real Graph API, webhook
   verify + signature check, test end-to-end with Meta's test WABA/number.
3. **Message loop**: dedupe, tenant routing, signed forward to tenant webhook, send
   reply back, message history storage.
4. **Hardening**: background queue instead of in-process tasks, encrypted secrets,
   structured logging/alerting, retry policy on tenant webhook calls.
5. **Compliance UX**: onboarding step documenting the AI-scope requirement; 24h window
   tracking; template message fallback.
6. **Fast-follows**: billing/metering, multi-number-per-user, media message support,
   coexistence flow for existing WhatsApp Business app numbers, admin dashboard.

## 12. Reference implementation (prototype, not production-ready)

A working prototype exists covering §3 steps 4–7 (onboarding, webhook verify, signed
tenant-forwarding loop) in FastAPI + SQLite, tested locally end-to-end with a simulated
Meta payload. Use it as a reference for the API contracts in §6, not as the codebase to
build on directly — it's missing everything in §9 and §10.

Files: `main.py`, `example_customer_webhook.py` (reference client), `requirements.txt`,
`.env.example`, `signup.html` (Embedded Signup frontend skeleton).

## 13. Open questions for the new project

- Do we host an optional built-in AI tier, or stay pure routing/orchestration forever?
- Multi-number-per-user — needed for v1 or a real fast-follow?
- Self-serve compliance attestation vs. manual review of each tenant's bot scope?
- Which queue/worker system (Celery+Redis, SQS+Lambda, etc.) fits the target deploy
  environment?

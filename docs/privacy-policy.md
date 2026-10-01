<!--
Source of truth for the Platform's Privacy Policy.

Live page: https://claude.ai/artifact/An1Tn3UZrw87dM4iAoAuQn
Pasted into: Meta App Dashboard → Settings → Basic → Privacy Policy URL
  (required before the app can go through App Review for WhatsApp Embedded Signup)

To update: edit this file, then have Claude republish it to the artifact URL above
(same URL — content changes in place, link doesn't change). Fill in every
[bracketed placeholder] with real values before submitting to Meta.
-->

# Privacy Policy

**Effective date:** September 30, 2026
**Applies to:** the WhatsApp AI Platform service

This policy explains what data the WhatsApp AI Platform ("the Platform," "we," "us") collects
when businesses ("Tenants") connect a WhatsApp Business number to their own AI assistant through
us, and when that assistant exchanges messages with the Tenant's customers ("End Users"). We act
as Meta's Tech Provider for this connection — we relay messages between WhatsApp and each
Tenant's own systems; we do not operate the chatbots ourselves.

## 1. Scope & roles

Two kinds of people interact with the Platform, and this policy covers both:

- **Tenants** — businesses that sign up for the Platform, connect a WhatsApp Business Account
  via Meta's Embedded Signup, and point it at their own AI bot or support system.
- **End Users** — people who message a Tenant's WhatsApp Business number. The Platform never
  operates a Tenant's bot; it forwards End User messages to the Tenant's own webhook and relays
  the reply back through WhatsApp.

A Tenant's own privacy practices for how *they* use their customers' messages are governed by
that Tenant's own privacy policy, not this one. This policy covers what the Platform itself — the
routing infrastructure in between — collects and does with data that passes through it.

## 2. Information we collect

**From Tenants:**
- Account details: name, email, password (stored hashed), API key
- WhatsApp Business Account ID, phone number ID, and a business access token, obtained through
  Meta's Embedded Signup flow
- The webhook URL and signing secret used to forward messages to the Tenant's own bot

**From End Users:**
- WhatsApp phone number
- Message content and timestamps sent to a Tenant's WhatsApp number
- Delivery and message-identifier metadata supplied by WhatsApp

We do not collect End User data directly — it reaches us only because a person chose to message
a Tenant's WhatsApp number, and WhatsApp delivers that message to us so we can route it.

## 3. How we use it

- **Message routing** — matching an incoming WhatsApp message to the right Tenant by phone
  number, and forwarding it to that Tenant's webhook.
- **Deduplication** — WhatsApp may redeliver the same message; we track message IDs we've
  already processed so a Tenant's bot doesn't see (or reply to) the same message twice.
- **Conversation context** — we keep recent message history per conversation so it can be
  included when forwarding to a Tenant's bot, letting the bot respond with context.
- **Fallback handling** — if a Tenant's bot fails to respond, times out, or returns an invalid
  reply, we send the End User a generic apology so the conversation doesn't hang silently.
- **Platform operation** — authenticating Tenants, and troubleshooting delivery issues.

We do not use End User message content to train models, build advertising profiles, or for any
purpose unrelated to delivering that message to the intended Tenant.

## 4. How it's shared

We share data with exactly two parties, both necessary to deliver a message end to end:

- **Meta / WhatsApp Business Platform** — sending and receiving messages happens through Meta's
  Graph API; Meta's own privacy policy governs its handling of that traffic.
- **The Tenant's own webhook** — each message is forwarded, HMAC-signed, to the specific
  Tenant's own AI system so it can generate a reply. We do not forward a Tenant's messages to
  any other Tenant.

We do not sell personal data, and we do not share it with any other third party.

## 5. Security

- Tenant access tokens and webhook secrets are encrypted at rest with AWS KMS before being
  stored.
- Requests forwarded to a Tenant's webhook are HMAC-SHA256 signed so the Tenant can verify they
  came from us.
- Incoming WhatsApp webhooks are signature-verified before being processed.
- Access to Tenant and message data is scoped per-Tenant and gated behind authenticated API
  access.

## 6. Retention

We retain message history for as long as a Tenant's account is active, so their bot can use
recent conversation context. If a Tenant closes their account, we delete their stored messages
and credentials within **[retention period, e.g. 30 days]**. Records we're required to keep for
security or legal reasons (such as fraud investigation) may be retained longer.

## 7. Your choices

**If you are an End User** messaging a business on WhatsApp: to stop a conversation, simply stop
messaging that number, or block it in WhatsApp. For questions about how a specific business uses
your messages, contact that business directly — their bot, their data practices.

**If you are a Tenant**: you can request a copy of, or deletion of, your account data and
message history by contacting us using the details below.

## 8. Children's privacy

The Platform is intended for business use and is not directed at children. We do not knowingly
collect data from anyone under 16 beyond what passes through as part of an End User's message to
a Tenant's WhatsApp number.

## 9. International transfers

Our infrastructure runs on Amazon Web Services in **[AWS region, e.g. us-east-1]**. Data may be
processed in a country other than the one you live in; where required, we rely on standard
contractual safeguards for any such transfer.

## 10. Changes to this policy

We'll update the effective date above whenever this policy changes, and for material changes
we'll notify Tenants by email before the change takes effect.

## 11. Contact us

**[Company / Legal Entity Name]**
Email: **[privacy@yourdomain.com]**
Mailing address: **[Street, City, State, ZIP, Country]**

---

*Draft prepared for Meta App Review submission — replace bracketed placeholders before
publishing as your live policy.*

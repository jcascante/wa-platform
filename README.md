# WhatsApp AI Platform

Multi-tenant WhatsApp AI chatbot platform. Full picture, conventions, and command reference
live in [`CLAUDE.md`](./CLAUDE.md) — read that first.

- [`whatsapp-ai-platform-spec/`](./whatsapp-ai-platform-spec/SPEC.md) — the spec and a
  reference-only prototype.
- [`service/`](./service) — the production service (FastAPI + Lambda + SQS worker).
- [`infra/terraform/`](./infra/terraform) — the AWS infrastructure.
- [`docs/privacy-policy.md`](./docs/privacy-policy.md) — Privacy Policy source; pasted URL lives
  in Meta App Dashboard → Settings → Basic → Privacy Policy URL, required for App Review.
- [`docs/meta-embedded-signup.md`](./docs/meta-embedded-signup.md) — Meta App / Embedded Signup
  configuration, local test setup, and current blocker (Business Verification).

## Quickstart

```
cd service
make up          # local Postgres + LocalStack
make install
make migrate
make dev          # http://localhost:8000
```

# WhatsApp AI Platform

Multi-tenant WhatsApp AI chatbot platform. Full picture, conventions, and command reference
live in [`CLAUDE.md`](./CLAUDE.md) — read that first.

- [`whatsapp-ai-platform-spec/`](./whatsapp-ai-platform-spec/SPEC.md) — the spec and a
  reference-only prototype.
- [`service/`](./service) — the production service (FastAPI + Lambda + SQS worker).
- [`infra/terraform/`](./infra/terraform) — the AWS infrastructure.

## Quickstart

```
cd service
make up          # local Postgres + LocalStack
make install
make migrate
make dev          # http://localhost:8000
```

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A multi-tenant WhatsApp AI chatbot platform. The platform acts as a Meta Tech Provider —
customers connect their own WhatsApp Business number via Embedded Signup, point it at their own
AI bot via a webhook, and this backend proxies messages between WhatsApp and that webhook.

Three top-level pieces:

- **`whatsapp-ai-platform-spec/`** — the spec (`SPEC.md`, source of truth for the target
  architecture) plus a throwaway FastAPI+SQLite prototype that validated the core loop
  end-to-end. Reference only — do not build on it directly (see its own notes in SPEC §12).
- **`service/`** — the production Python service: the FastAPI app, the SQS-driven worker, and
  everything deployed to AWS. This is where feature work happens.
- **`infra/terraform/`** — the AWS infrastructure as Terraform.

## Commands

All from `service/`:

```
make install      # pip install -e ".[dev]"
make up            # local Postgres + LocalStack (SQS/KMS) via docker compose
make dev            # uvicorn with reload, port 8000
make test           # pytest
make lint           # ruff check
make fmt             # ruff format + fix
make typecheck       # mypy
make migration m="add x"   # generate an alembic migration from model changes
make migrate         # alembic upgrade head (local)
make package          # build the Lambda deployment zip all three Lambdas share
make test-live        # hits the real Meta Graph API — needs META_TEST_* env vars, see tests/live/README.md
```

Single test: `pytest tests/unit/test_security.py::test_signature_roundtrip` (same `pytest`
node-id syntax for any test file).

From `infra/terraform/`: `terraform fmt -recursive`, then from a root config directory
(`bootstrap/`, or `envs/<name>/`), `terraform init && terraform plan`. See
`infra/terraform/README.md` for the full bootstrap-through-deploy sequence.

CI (`.github/workflows/ci.yml`) runs `service`'s lint/typecheck/test (excluding `tests/live/`)
and `terraform fmt -check` + `validate` for `bootstrap/` and every environment under
`infra/terraform/envs/`. **Deploy** (`.github/workflows/deploy.yml`) is separate and manual
(Actions tab → Deploy → Run workflow): builds the package, applies Terraform, runs migrations.
Gated behind the `production` GitHub Environment's required reviewers and GitHub OIDC (no
stored AWS credentials) — see `infra/terraform/README.md` for the one-time bootstrap a human
has to do before this works.

## Architecture

**Compute: AWS Lambda, not ECS/EKS.** Chosen to start with near-zero idle cost (pay-per-request)
while traffic is low; SPEC §13 explicitly left the queue/worker system open, and SPEC's
ack-fast/background-worker design (§10) maps cleanly onto Lambda without needing a
long-running process. Revisit if cold starts or per-invocation overhead become a real problem —
see `infra/terraform/README.md`.

- **`service/src/wa_platform/lambda_handlers/api_handler.py`** — API Gateway HTTP API →
  Lambda running the FastAPI app (`api/app.py`) via Mangum. Handles `/auth/*`,
  `/onboarding/complete`, `/me`, `/me/webhook`, and the Meta-facing `/webhook`.
- **`/webhook` POST** verifies Meta's `X-Hub-Signature-256`, then enqueues to SQS
  (`integrations/sqs.py`) and returns 200 immediately — it does **not** do dedupe, tenant
  lookup, or forwarding inline (SPEC §10: ack Meta within a few seconds, do the real work off
  the request path).
- **`service/src/wa_platform/lambda_handlers/worker_handler.py`** — SQS-triggered Lambda that
  drains that queue and runs `workers/message_processor.py`: dedupe on `wa_message_id`
  (must happen before any side effect — Meta retries deliveries), tenant lookup by
  `phone_number_id` (single shared queue/endpoint for every tenant, never assume one tenant per
  deployment), forward to the tenant's own webhook (signed, SPEC §6 contract), record history,
  send the reply back via the Meta Graph API. Reports `batchItemFailures` so one bad message in
  a batch doesn't block or duplicate-process the rest.
- **Outbound-to-tenant contract**: POST `{tenant_id, from, message, history}` to
  `tenant.webhook_url`, HMAC-SHA256-signed via `X-Platform-Signature` (key = that tenant's
  `webhook_secret`). Expects `200 {"reply": "..."}` within 30s; any network failure, non-2xx, or
  malformed reply degrades to a generic apology sent to the WhatsApp user — a broken tenant bot
  must never break the platform (`_forward_to_tenant_webhook` in `message_processor.py`).
- **Auth**: bearer API-key (`current_user_id` in `api/deps.py`) — no session/JWT. Every query
  touching `tenants`/`messages` must derive its tenant scope from this, never from a
  client-supplied id — this is the platform's core security boundary (see the
  `tenant-isolation-reviewer` agent below).
- **Secrets at rest**: `business_token` and `webhook_secret` are KMS-encrypted via `Encryptor`
  (`core/security.py`) before they touch Postgres — SPEC §9 flagged the prototype's plaintext
  storage as a must-fix. Meta app credentials live in Secrets Manager, not in Terraform state or
  Lambda env vars directly; `core/config.py`'s `_hydrate_from_secrets_manager` resolves the ARNs
  Terraform wires in (`DATABASE_URL_SECRET`, `META_APP_SECRET_ARN`) into plain env vars once per
  Lambda cold start.
- **Data model**: `users`, `tenants`, `messages`, `processed_messages` — matches SPEC §5 exactly
  (`db/models.py`). Migrations are hand-reviewed Alembic (`migrations/versions/`) — autogenerate
  is a starting point, not something to trust blindly for renames or server-side defaults.
- **Meta Graph API calls**: `integrations/meta/client.py`, covered by mocked `respx` tests
  (`tests/unit/test_meta_client.py`) in the default suite, plus a separate real-API check in
  `tests/live/` gated behind live sandbox credentials (never runs in CI — see
  `tests/live/README.md`). Add a mocked test for any new Graph API call; add a live one only
  when there's a specific contract question mocks can't answer.

## Infrastructure (`infra/terraform/`)

`bootstrap/` (remote state storage — S3, with S3's native lockfile locking, applied once
manually, never touched again), `envs/<name>/` per environment (currently `dev`), shared
modules under `modules/`:
`network` (VPC with public subnets for the bastion and private subnets — behind one NAT
gateway — for Lambda + RDS; Lambda-in-VPC never gets a public IP on its ENI, so NAT is the only
way to give it internet access without pulling it out of the VPC), `database` (single-AZ
`db.t4g.micro` Postgres, storage-encrypted — cheapest managed option, explicit
upgrade path noted for Multi-AZ/RDS Proxy), `queue` (plain SQS + DLQ, no broker), `secrets`
(the KMS key + the Meta-app Secrets Manager entry), `lambda_api`, `lambda_worker`,
`lambda_migrate` (runs `alembic upgrade head` from inside the VPC — CI can't reach RDS
directly), `bastion` (SSM-only EC2, no SSH/public ingress, for ad-hoc `psql`/debugging —
deliberately separate from `lambda_migrate`: automation shouldn't depend on a human-managed box
being up), `github_oidc` (lets GitHub Actions deploy with zero stored AWS credentials, scoped
to the `production` GitHub Environment). Full detail and the bootstrap sequence:
`infra/terraform/README.md`.

Cost/security posture: every module defaults to the cheapest option that works, with a comment
at the decision point naming what to reach for once load justifies it. Don't add HA/scaling
infra ahead of actual need — that tradeoff is deliberate, not an oversight. One exception flagged
rather than fixed: the GitHub deploy role's IAM policy is intentionally broad (`iam:*` etc.) —
a real privilege-escalation risk accepted for v1 simplicity, documented in
`modules/github_oidc/main.tf` and `infra/terraform/README.md`.

## Compliance constraints that shape design decisions

- Meta's general-purpose AI chatbot ban (in force since 2026-01-15): each tenant's bot must be
  scoped to their own business use case (support, bookings, FAQs), not an open-domain assistant.
  Relevant to any onboarding/review flow work.
- 24-hour customer service window: free-form replies only work within 24h of the WhatsApp user's
  last message; outside it, a pre-approved template is required. Not yet implemented — v1 just
  sends a generic failure message when a send fails for this reason (Meta error code 131047).

## AI-assisted workflow (`.claude/`)

- **Skills** (`.claude/skills/`) — `add-api-endpoint`, `add-db-migration`, `terraform-change`.
  Load one whenever a task fits its shape; each documents this repo's specific conventions
  rather than generic advice.
- **Agents** (`.claude/agents/`) — `tenant-isolation-reviewer` (cross-tenant data-leak /
  IDOR review — run on any change touching `api/`, `db/`, or `workers/`) and
  `terraform-cost-reviewer` (catches infra changes that silently abandon the cheap-by-default
  posture, plus security misconfigurations). Both are referenced from the skills above as a
  "run this before calling the change done" step — invoke them proactively on non-trivial
  changes in their area rather than waiting to be asked.

## Open questions (carried over from SPEC §13, still unresolved)

- Optional built-in AI tier vs. staying pure routing/orchestration forever.
- Multi-number-per-user — v1 or fast-follow?
- Self-serve compliance attestation vs. manual review of each tenant's bot scope.

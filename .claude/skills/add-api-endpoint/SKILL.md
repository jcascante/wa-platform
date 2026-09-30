---
name: add-api-endpoint
description: Add a new FastAPI endpoint to the wa-platform service following its layering convention (schema → router → app registration → test). Use when asked to add, change, or remove an API route in service/.
---

# Adding an API endpoint

This service separates each endpoint into three layers. Follow all of them — don't put
business logic directly in a router function beyond orchestration.

1. **Schema** (`service/src/wa_platform/schemas/<domain>.py`): Pydantic request/response
   models. Reuse an existing domain file if the endpoint fits one (`auth.py`, `tenant.py`,
   `webhook.py`); create a new file only for a genuinely new domain.
2. **Router** (`service/src/wa_platform/api/routers/<domain>.py`): the endpoint function.
   - Auth: depend on `current_user_id` from `wa_platform.api.deps` for anything requiring a
     logged-in platform user — never trust a `tenant_id`/`user_id` from the request body.
   - DB: depend on `get_db` from `wa_platform.db.session`.
   - Secrets: never read or write `business_token` / `webhook_secret` in plaintext — go
     through `Encryptor` (`wa_platform.core.security`, injected via `get_encryptor`).
   - Keep the function thin: validate via the schema, call into `db`/`integrations`, return
     the response schema. Push real logic into `workers/` or `integrations/` if it's more
     than a few lines, so it's reusable from the SQS worker too.
3. **Registration** (`service/src/wa_platform/api/app.py`): add `app.include_router(...)` if
   this is a new router module.
4. **Test** (`service/tests/integration/test_<domain>_api.py`): a `TestClient` test per new
   behavior, following the pattern in `test_auth_api.py` (SQLite `get_db` override). Add a
   unit test in `tests/unit/` instead if you're testing pure logic (schema validation, a
   helper function) with no HTTP/DB involved. Any new call to the Meta Graph API gets a mocked
   `respx` test in `tests/unit/test_meta_client.py` (see that file for the pattern) — never a
   real HTTP call in the default test suite. A change that specifically needs verifying
   against Meta's real API belongs in `tests/live/` instead (gated behind live credentials,
   see `tests/live/README.md`), not in the default suite.

After changes: `make lint && make typecheck && make test` from `service/`.

## Multi-tenant isolation — the one rule that matters most here

Every query that touches `tenants`, `messages`, or anything tenant-scoped **must** filter by
the `tenant_id` derived from `current_user_id`, never by a `tenant_id` supplied in the request.
This is the platform's core security boundary (SPEC §2) — a missing filter here is a
cross-tenant data leak. If you're touching a router or worker function, it's worth invoking the
`tenant-isolation-reviewer` agent on the diff before considering the change done.

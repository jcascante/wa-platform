# Meta / WhatsApp Embedded Signup — setup notes

How this app's Meta App is configured for Embedded Signup, what's been built to test it
locally, and where we left off. Secrets (App Secret, access tokens, webhook verify token) live
in `.meta` (repo root) and `service/.env` — both gitignored, never duplicated here.

## Current status (as of 2026-10-01)

**Blocked on Business Verification.** Meta's own "Exchange Token" test tool (App Dashboard →
WhatsApp → Embedded Signup → Getting Started) reproduces the same `OAuthException code 100,
error_subcode 36008` ("redirect_uri mismatch") using its own internally-generated `code` and its
own correct `redirect_uri` — which means every retry we did (different HTTP method, API
version, `grant_type`, `redirect_uri` value) was never going to fix it. The Getting Started page
states outright: *"You will not be able to onboard users until you complete business
verification."* That's the actual gate.

**Next step**: complete Business Verification for the business in Meta Business Settings
(Security Center → Business Verification). Once that clears, retry
`/dev/embedded-signup` end to end — no further code changes should be needed.

**Secondary, not currently blocking**: App Review & Access Verification are also incomplete.
Fine for testing as the account that's the app's Admin (1 admin / 0 developers currently); anyone
else testing needs to be added manually under App Roles first.

## Meta App Dashboard configuration

App ID `1101098552292681` (Tech Provider model — see `CLAUDE.md` "What this repo is". Given this
architecture — one app managing other businesses' WABAs via Embedded Signup — Tech Provider
status and Business Verification are required by Meta, not optional; see "Current status"
above.)

- **WhatsApp product** — added, provisions the Test WABA (see `.meta` for its number/IDs).
- **Facebook Login for Business product** — added (separate from the WhatsApp product; this is
  where Embedded Signup configurations actually live — easy to miss if you only look at the
  WhatsApp product panel).
  - **Configurations** → created one with Login Variation = *WhatsApp Embedded Signup* → its
    Configuration ID (`config_id`) is in `.meta`.
  - **Client OAuth Settings**:
    - *Login with the JavaScript SDK*: **Yes** (was No by default — flip this or `FB.login` never
      runs).
    - *Enforce HTTPS*: forced **Yes**, can't be disabled → `http://localhost` redirect URIs are
      rejected outright regardless of being in the allowlist. Local testing needs an HTTPS
      tunnel (see below).
    - *Valid OAuth Redirect URIs*: needs the exact page URL that calls `FB.login`, full path
      included (e.g. `https://<tunnel-host>/dev/embedded-signup`). Also doubles as the allowlist
      the JS SDK uses for in-app-browser popups.
    - *Allowed Domains for the JavaScript SDK*: same host, **bare origin only** (no path).
  - Basic Settings → **App Domains**: also needs the tunnel hostname (bare domain), separate
    from the two fields above — without it the popup fails with "Can't load URL: the domain of
    this URL isn't included in the app's domains" before Login even runs.
- **Graph API version**: using `v26.0` everywhere (FB SDK init + server-side token exchange),
  matching what Meta's own generated code sample for this app uses. `service/.env`'s
  `GRAPH_VERSION` must match.

None of the above is the current blocker — all confirmed correctly configured. Documented since
each one produced a distinct, confusing error before being found (see "What we hit" below).

## Local dev setup for testing this flow

```
cd service
make up            # Postgres + LocalStack, now also bootstraps the SQS queue + KMS key/alias
make dev            # FastAPI app, port 8000
make worker          # drains the local SQS queue same as the AWS worker Lambda
```

Then, since Embedded Signup needs HTTPS and `localhost` is rejected (see Enforce HTTPS above):

```
cloudflared tunnel --url http://localhost:8000     # installed via `brew install cloudflared`
```

Run via `! cloudflared tunnel ...` (the `!` prefix) if asking Claude to do it — starting a public
tunnel is a permission-gated action in this session, not something run automatically. Each
restart gives a new random hostname, which then has to be re-added to the three Meta fields
above (App Domains, Valid OAuth Redirect URIs, JS SDK Allowed Domains) and re-tested from that
new URL (browser `localStorage` — the API key field — doesn't carry over between hostnames
either). A persistent/named tunnel would remove this friction if this becomes a recurring test
cycle.

Open `https://<tunnel-host>/dev/embedded-signup` (not `localhost:8000`) and work top to bottom:
register a test user → Launch WhatsApp Signup → Complete onboarding. Full details on each step
are in the page itself.

## Code changes made getting here

- **`service/src/wa_platform/api/routers/dev_tools.py`** (new) — the test harness page above,
  served at `GET /dev/embedded-signup`. Same-origin fetches to `/auth/*` and
  `/onboarding/complete`, so no CORS needed. Persists email/API key/config ID to
  `localStorage` (per-origin, so lost across tunnel restarts).
- **`service/src/wa_platform/api/app.py`** — wires that router in, but only when
  `ENVIRONMENT != "prod"` (checked via `os.environ` directly, not through `Settings`/Secrets
  Manager, so it can't affect Lambda cold-start behavior).
- **`service/src/wa_platform/integrations/meta/client.py`** — `exchange_code()`:
  - now takes a `redirect_uri` param instead of omitting it.
  - switched from `GET` with query params to `POST` with a JSON body including an explicit
    `grant_type: "authorization_code"`, matching Meta's own generated code sample for this app
    (the old `GET`-with-query-params form is what most third-party guides show, but isn't what
    Meta's own tooling actually sends).
- **`service/src/wa_platform/schemas/tenant.py`** — `OnboardingIn` gained `redirect_uri: str =
  ""`, threaded through from the test page (`window.location.href`) to the exchange call.
- **`service/src/wa_platform/api/routers/onboarding.py`** — the `MetaGraphError` log line now
  includes Meta's actual response body (`exc.response.text`), not just the status code — this is
  what let us see the real `36008`/business-verification error instead of guessing from a
  generic "failed to connect" message.
- **`service/tests/unit/test_meta_client.py`** — mocks updated from `respx.get` to `respx.post`
  for `oauth/access_token` to match the above.
- **`service/scripts/localstack_bootstrap.sh`** (new) — creates the SQS queue and KMS key/alias
  in LocalStack; wired into `make up`. Nothing provisioned these before — `/webhook` and
  `Encryptor` would fail against a fresh LocalStack without this.
- **`service/scripts/local_worker.py`** (new, `make worker`) — polls that queue and feeds
  batches into the real `worker_handler.handler`, so `/webhook → SQS → tenant webhook forward`
  is testable locally end to end, same code path AWS runs.
- **`service/Makefile`** — added the `worker` target; `up` now also runs the bootstrap script.

## What we hit, in order (for next time this breaks differently)

1. `uvicorn: No such file` — `make dev` run outside the venv; needs `source .venv/bin/activate`
   first (or use `.venv/bin/uvicorn` directly).
2. 401 `missing bearer token` / `invalid api key` — repeatedly caused by either page reloads
   losing the (unpersisted, at the time) API key field, or logging in instead of registering
   (`/auth/login` never returns an `api_key` by design — only `/auth/register` and key-rotation
   do).
3. `invalid credentials` on login — `.meta`'s saved test user is stale against whatever the
   local Postgres container's current state is; the local DB got wiped at least once
   independently of any `make down`/volume issue we could pin down. Treat the local DB as
   disposable — don't rely on `.meta`'s saved credentials matching it.
4. `Can't load URL: domain not in app's domains` — App Domains (Basic Settings), not yet set.
5. `OAuthException 100/36008` (redirect_uri mismatch), persistent across every parameter
   combination we tried — root-caused to Business Verification, not redirect_uri at all (see
   "Current status" above). Confirmed by reproducing the identical error through Meta's own
   Exchange Token tool using its own correct parameters.

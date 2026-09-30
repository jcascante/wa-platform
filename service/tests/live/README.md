# Live Meta Graph API tests

Everything in `tests/unit/test_meta_client.py` mocks the Graph API with `respx` — fine for
verifying our request/response handling, but it can't catch a real contract drift (Meta
changing a field name, a permission we don't actually have yet, a v23.0 → v24.0 behavior
change). These tests fill that gap by hitting Meta's real API with a test WABA/number.

**Not run by CI or by default `pytest`** — `pyproject.toml` scopes `testpaths` to
`tests/unit`/`tests/integration` specifically to exclude this directory. Run explicitly:

```
make test-live
```

## Requirements

You need a test WABA + test phone number from Meta's **API Setup** page (SPEC §7 — the same
one used for manual local development), plus a system-user access token with
`whatsapp_business_management` + `whatsapp_business_messaging`. Set:

```
META_TEST_APP_ID=...
META_TEST_APP_SECRET=...
META_TEST_ACCESS_TOKEN=...          # system-user token, long-lived
META_TEST_WABA_ID=...
META_TEST_PHONE_NUMBER_ID=...
META_TEST_RECIPIENT_WA_ID=...       # a WhatsApp number that can receive the test message
```

If these aren't set, every test in this directory skips itself (see `conftest.py`) rather than
failing — safe to leave configured or not.

## Scope

Currently just `test_meta_graph_live.py`: `subscribe_app` and `send_text` against the real
API. **Deliberately not covering** `exchange_code` (Embedded Signup's `code` is single-use and
short-lived — can't be scripted into a repeatable test without a browser flow) or
`register_number` (registering/deregistering a real number repeatedly is disruptive and slow).
Add more here as specific Meta-contract questions come up, rather than trying to mirror every
mocked test 1:1.

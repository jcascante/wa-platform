---
name: add-db-migration
description: Change the wa-platform database schema — add/modify a table or column, add an index. Use whenever a task requires editing service/src/wa_platform/db/models.py.
---

# Changing the schema

1. Edit `service/src/wa_platform/db/models.py` (SQLAlchemy 2.0 `Mapped[...]` style — follow
   the existing models for the pattern).
2. Generate the migration: `cd service && make migration m="short description"`.
3. **Read the generated file in `migrations/versions/` before running it.** Alembic's
   autogenerate misses some things — renamed columns show as drop+add (data loss), and it
   never infers `server_default` intent correctly. Check both `upgrade()` and `downgrade()`.
4. Apply locally: `make migrate` (needs `make up` running for local Postgres).
5. Any column holding a tenant secret (`business_token`, `webhook_secret`, or similar) must
   be encrypted before it reaches the database — never add a plaintext secret column. Route
   it through `Encryptor` (`wa_platform.core.security`) exactly like the existing columns do.

In production, the `Deploy` GitHub Actions workflow runs `alembic upgrade head` automatically
after every apply, via the `lambda_migrate` module (a Lambda in the same VPC as RDS — the CI
runner itself can't reach the private subnet). For ad-hoc production queries or debugging
(not migrations), use the SSM bastion — see "Ad-hoc DB access" in `infra/terraform/README.md`.

---
name: terraform-change
description: Make or review a change to the AWS infrastructure under infra/terraform. Use for anything touching infra/terraform/modules or infra/terraform/envs.
---

# Changing the infrastructure

This project defaults to the **cheapest option that works**, with an explicit upgrade path
noted in a comment wherever a cheap choice will need revisiting at scale (see
`infra/terraform/README.md` for the current picks: Lambda, single-AZ `db.t4g.micro`, plain
SQS). Match that pattern for new changes — pick the cheap default, leave a comment naming what
to reach for when load actually requires it. Don't preemptively add HA/scaling infra nobody
has asked for yet.

## Workflow

1. Add/change resources in the relevant `modules/<name>/` (or a new module for a genuinely new
   piece of infra — don't grow an existing module past one clear responsibility).
2. Wire it into `envs/dev/main.tf` (and any other env that should get it).
3. `terraform fmt -recursive` from `infra/terraform/`.
4. `terraform -chdir=envs/dev init -backend=false && terraform -chdir=envs/dev validate`.
5. For anything beyond a trivial variable/output change, run `terraform plan` against real
   credentials and read the plan output before applying — Terraform applies are not easily
   reversible for stateful resources (RDS, KMS keys with data encrypted under them).

## Non-negotiables, even on the cheap path

- No resource holding tenant secrets or credentials is ever publicly accessible (RDS
  `publicly_accessible = false`, security groups scoped to the Lambda SG only — see
  `modules/network`).
- Tenant secrets (`business_token`, `webhook_secret`) are encrypted via the KMS key in
  `modules/secrets` — never introduce a second, app-managed encryption scheme.
- New IAM policies are scoped to the specific resource ARN, never `Resource = "*"`.

Invoke the `terraform-cost-reviewer` agent on any non-trivial infra change before considering
it done — it checks specifically for accidental cost blowups (oversized instances, NAT
gateways, provisioned-capacity resources) and the security items above.

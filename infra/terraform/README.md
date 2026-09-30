# Infrastructure

Terraform. `bootstrap/` (remote state storage, applied once), `envs/<name>/` per environment
(currently `dev`), shared building blocks under `modules/`.

## What this deploys (dev)

- **network** — a VPC with 2 public subnets (bastion only — the one thing here with a public IP)
  and 2 private subnets (Lambda + RDS) behind a single NAT gateway. Lambda-in-VPC never gets a
  public IP on its ENI even in a public subnet, so a NAT gateway is the only way to keep it in
  the VPC with real internet access (Secrets Manager, KMS, SQS, Meta, tenant webhooks) — one
  gateway, not one per AZ, to halve the ~$32/mo fixed cost.
- **database** — single-AZ RDS Postgres `db.t4g.micro`, storage-encrypted. Cheapest managed
  Postgres; move to Multi-AZ / a bigger class / add RDS Proxy once real traffic justifies the cost.
- **queue** — one SQS queue + DLQ (5 receives before dead-lettering). No broker to run. Optional
  CloudWatch alarm + SNS email subscription on the DLQ (set `alert_email` in tfvars).
- **secrets** — one KMS key (tenant secret encryption) + one Secrets Manager secret for the
  Meta app credentials.
- **lambda_api** — API Gateway HTTP API → Lambda running the FastAPI app via Mangum.
- **lambda_worker** — SQS → Lambda, `ReportBatchItemFailures` so one bad message doesn't
  block or duplicate-process the rest of the batch.
- **lambda_migrate** — a Lambda that runs `alembic upgrade head` from inside the VPC. Invoked
  manually or by the deploy workflow after every apply — the CI runner itself has no network
  path to RDS in the private subnet, but a Lambda in the same VPC does.
- **bastion** — an SSM-only EC2 instance (no SSH, no public ingress) for ad-hoc RDS access —
  `psql`, one-off debugging queries. Separate from `lambda_migrate` on purpose: automated
  migrations shouldn't depend on a human-managed box being up, and ad-hoc debugging needs a
  real shell, not a fixed Lambda payload. See "Ad-hoc DB access" below.
- **github_oidc** — lets GitHub Actions deploy without stored AWS credentials. Trust policy is
  scoped to this repo's `production` GitHub Environment specifically.

All three Lambdas share one deployment package (`package_path`) built from `service/`.

## First-time setup (bootstrap)

Remote state is required, not optional, once CI deploys: GitHub Actions runners are ephemeral,
so state can't live on a runner's disk between runs. Steps 1–2 are manual, run once by a human
with real AWS credentials; CI takes over from step 3 onward.

**1. Create the state bucket** (its own local-state config — a backend's storage can't be
managed by Terraform configured to use that backend). Locking is S3's native lockfile
(conditional writes, Terraform >= 1.10) — no DynamoDB table:

```
cd infra/terraform/bootstrap
terraform init
terraform apply -var="state_bucket_name=wa-platform-tfstate-<pick-a-unique-suffix>"
```

**2. First apply of `envs/dev`**, from your own machine:

```
cd ../envs/dev
cp backend.hcl.example backend.hcl          # fill in the bucket name from step 1
cp terraform.tfvars.example terraform.tfvars  # fill in github_repo = "owner/repo"
terraform init -backend-config=backend.hcl

cd ../../../../service && make package && cd -
terraform plan
terraform apply
```

Then, in the GitHub repo: **Settings → Environments → New environment → `production`**, add
required reviewers (this is what gates the OIDC role — see `modules/github_oidc`). **Settings →
Secrets and variables → Actions → Variables**, add:
- `AWS_DEPLOY_ROLE_ARN` = the `github_deploy_role_arn` output from the apply above
- `TF_STATE_BUCKET` = the bucket name from bootstrap step 1 (CI can't read the gitignored
  `backend.hcl`, so the Deploy workflow passes backend config as CLI flags from this instead)
- `AWS_REGION` if not `us-east-1`

Populate the Meta app credentials (Terraform intentionally does not manage these — see SPEC §7
for where they come from):

```
aws secretsmanager put-secret-value \
  --secret-id wa-platform-dev-meta-app \
  --secret-string '{"meta_app_id":"...","meta_app_secret":"...","webhook_verify_token":"..."}'
```

Run the first migration (see "Running migrations" below).

**3. From here on**, run the **Deploy** workflow (Actions tab → Deploy → Run workflow) for any
infra or app change — it builds the package, deploys and runs the migration Lambda *first*
(new app code may depend on the schema change it makes), then plans and applies everything
else. See `.github/workflows/deploy.yml`.

## Running migrations

Automated (CI, after every deploy) or manual:

```
aws lambda invoke --function-name wa-platform-dev-migrate --payload '{}' /tmp/out.json && cat /tmp/out.json
```

## Ad-hoc DB access

Via the bastion + SSM (no SSH key, nothing to open on the security group):

```
aws ssm start-session --target <bastion_instance_id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<rds endpoint, no port>"],"portNumber":["5432"],"localPortNumber":["15432"]}'

# in another terminal:
psql "postgresql://platform:<password from Secrets Manager>@localhost:15432/platform"
```

Stop the bastion when not in use — it costs nothing idle beyond ~$1/mo of EBS storage:
`aws ec2 stop-instances --instance-ids <bastion_instance_id>`.

## State

S3, with native S3 locking (`use_lockfile = true`, Terraform >= 1.10) — no DynamoDB table (see
bootstrap above). `envs/dev/main.tf`'s `backend "s3" { use_lockfile = true }` block is partial
config — bucket/key/region live in the gitignored `backend.hcl`, not committed (see
`backend.hcl.example`).

## Why Lambda over ECS/Fargate

Chosen for v1 to minimize idle cost (pay-per-request, nothing running between messages) at the
cost of cold starts and a 15-minute execution ceiling neither of which bite this workload yet
(SPEC's webhook-ack-fast / background-worker model already assumes short-lived executions).
Revisit if traffic makes cold starts or per-invocation overhead a real cost or latency problem.

## Known tradeoff worth flagging

The GitHub Actions deploy role (`modules/github_oidc`) holds broad `iam:*`/`ec2:*`/etc.
permissions rather than a tightly scoped policy — documented in that module as a real
privilege-escalation risk accepted for v1 simplicity, not an oversight. Revisit with a
permissions boundary before this AWS account holds anything more sensitive than this one
service.

# Lets GitHub Actions assume an AWS role without any stored AWS credentials. The trust policy
# is scoped to this repo's `production` GitHub Environment specifically (not just any branch)
# — the deploy workflow uses `environment: production`, which GitHub gates behind the manual
# approval configured on that environment, so this role is only assumable after a human clicks
# approve.
#
# Thumbprint is fetched live from GitHub's OIDC endpoint rather than hardcoded: GitHub has
# rotated this certificate before (2023), which silently breaks a hardcoded thumbprint until
# someone notices deploys failing. AWS also doesn't actually validate the thumbprint against
# the presented cert for well-known OIDC providers like this one — it's a required argument
# that's effectively vestigial — so fetching it live costs nothing and removes a staleness trap.

data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github.certificates[0].sha1_fingerprint]
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:environment:${var.github_environment}"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name               = "${var.name}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# Intentionally broad: Terraform manages VPC/RDS/SQS/Lambda/API Gateway/IAM/KMS/Secrets Manager
# resources end to end, so the deploy role needs create/modify access across all of them. Scope
# this down with a permissions boundary once this account runs more than one workload — not
# worth the upfront complexity for a single-service v1.
#
# Known real risk, not just "less scoped than ideal": `iam:*` on a role that GitHub Actions can
# assume is a privilege-escalation path — a compromised workflow, a malicious PR that gets
# accidentally approved into the protected environment, or a bug in this Terraform could grant
# this role (or a new one) broader access than intended, including admin. Accepted for now
# because a hand-enumerated policy covering every Terraform-managed resource type is a lot of
# upfront surface area to get right for a single-service v1; revisit with a permissions boundary
# or scoped iam:CreateRole/PutRolePolicy conditions (e.g. restricted to role names prefixed
# "wa-platform-") before this account holds anything more sensitive.
data "aws_iam_policy_document" "deploy" {
  statement {
    sid    = "BroadInfraManagement"
    effect = "Allow"
    actions = [
      "ec2:*",
      "rds:*",
      "sqs:*",
      "kms:*",
      "secretsmanager:*",
      "lambda:*",
      "apigateway:*",
      "logs:*",
      "iam:*",
      "ssm:*",
      "sts:GetCallerIdentity",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "${var.name}-github-deploy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}

# One KMS key for envelope-encrypting tenant secrets at rest (business_token, webhook_secret —
# SPEC §9). App code calls kms:Encrypt/Decrypt directly (core/security.py Encryptor) rather than
# managing a Fernet key ourselves, so key rotation and audit trail come from AWS for free.

resource "aws_kms_key" "tenant_secrets" {
  description             = "${var.name} tenant secret encryption (business_token, webhook_secret)"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_alias" "tenant_secrets" {
  name          = "alias/${var.name}"
  target_key_id = aws_kms_key.tenant_secrets.key_id
}

resource "aws_secretsmanager_secret" "meta_app" {
  name = "${var.name}-meta-app"
}

# Populate META_APP_ID / META_APP_SECRET / WEBHOOK_VERIFY_TOKEN via `aws secretsmanager
# put-secret-value` after the Meta app is created (SPEC §7) — not committed to Terraform state.

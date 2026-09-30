output "kms_key_id" {
  value = aws_kms_alias.tenant_secrets.name
}

output "kms_key_arn" {
  value = aws_kms_key.tenant_secrets.arn
}

output "meta_app_secret_arn" {
  value = aws_secretsmanager_secret.meta_app.arn
}

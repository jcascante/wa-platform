output "api_invoke_url" {
  value = module.lambda_api.invoke_url
}

output "db_endpoint" {
  value = module.database.endpoint
}

output "queue_url" {
  value = module.queue.queue_url
}

output "kms_key_id" {
  value = module.secrets.kms_key_id
}

output "migrate_function_name" {
  value = module.lambda_migrate.function_name
}

output "bastion_instance_id" {
  value = module.bastion.instance_id
}

output "github_deploy_role_arn" {
  value = module.github_oidc.deploy_role_arn
}

output "instance_name" {
  description = "Name of the compute instance"
  value       = module.dev-caa.instance_name
}

output "instance_external_ip" {
  description = "External IP address of the instance"
  value       = module.dev-caa.instance_external_ip
}

output "instance_internal_ip" {
  description = "Internal IP address of the instance"
  value       = module.dev-caa.instance_internal_ip
}

output "service_account_email" {
  description = "Email of the service account"
  value       = module.dev-caa.service_account_email
}
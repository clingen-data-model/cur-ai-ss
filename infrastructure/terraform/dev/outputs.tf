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

output "docling_service_url" {
  description = "HTTPS URL of the docling Cloud Run service"
  value       = module.docling-service.url
}

output "docling_staging_bucket" {
  description = "Bucket for docling input PDFs and result archives"
  value       = module.docling-service.staging_bucket
}

output "docling_image_repository" {
  description = "Artifact Registry path docling images are pushed to"
  value       = module.docling-service.image_repository
}

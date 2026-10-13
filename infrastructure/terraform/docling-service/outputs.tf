output "url" {
  description = "HTTPS URL of the service (call with an ID token whose audience is this URL)"
  value       = google_cloud_run_v2_service.this.uri
}

output "staging_bucket" {
  description = "Bucket for input PDFs and result archives"
  value       = google_storage_bucket.staging.name
}

output "image_repository" {
  description = "Artifact Registry path images are pushed to"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.this.repository_id}"
}

output "service_account_email" {
  value = google_service_account.this.email
}

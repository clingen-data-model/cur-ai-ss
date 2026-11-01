output "service_url" {
  description = "Base URL of the PDF parsing service; the worker's PDF_PARSING_SERVICE_URL"
  value       = google_cloud_run_v2_service.pdf_parsing.uri
}

output "image_repository" {
  description = "Where the build workflow pushes the service image"
  value       = "${local.registry}/${google_artifact_registry_repository.images.repository_id}/server"
}

output "workload_identity_provider" {
  description = "What .github/workflows/pdf-parsing-image.yml authenticates with"
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "builder_service_account" {
  description = "The account the build workflow and bin/build-pdf-parsing-image run as"
  value       = google_service_account.builder.email
}

output "exchange_bucket" {
  description = "Bucket the worker and the service pass a paper's files through"
  value       = google_storage_bucket.exchange.name
}

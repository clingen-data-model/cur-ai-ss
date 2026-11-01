output "service_url" {
  description = "Base URL of docling-serve; the worker's DOCLING_SERVE_URL"
  value       = google_cloud_run_v2_service.docling.uri
}

output "image" {
  description = "The image the service runs"
  value       = local.image
}

output "exchange_bucket" {
  description = "Bucket the worker and the service pass a paper's files through"
  value       = google_storage_bucket.exchange.name
}

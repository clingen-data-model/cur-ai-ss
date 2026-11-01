output "service_url" {
  description = "Base URL of the PDF parsing service; the worker's PDF_PARSING_SERVICE_URL"
  value       = google_cloud_run_v2_service.pdf_parsing.uri
}

output "image" {
  description = "The image the service runs"
  value       = local.image
}

output "exchange_bucket" {
  description = "Bucket the worker and the service pass a paper's files through"
  value       = google_storage_bucket.exchange.name
}

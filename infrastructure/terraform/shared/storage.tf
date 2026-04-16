# GCS bucket for static resources
resource "google_storage_bucket" "static_resources" {
  name          = "caa-static-resources"
  location      = "US"
  force_destroy = false

  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  versioning {
    enabled = false
  }
}

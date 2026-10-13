locals {
  apis = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# Where deploy builds push the image (bin/deploy-docling-service)
resource "google_artifact_registry_repository" "this" {
  project       = var.project_id
  location      = var.region
  repository_id = var.name
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}

# Transient hand-off area: the worker uploads a PDF, the service uploads the
# result archive. Nothing here is the system of record, so objects expire.
resource "google_storage_bucket" "staging" {
  project                     = var.project_id
  name                        = "${var.project_id}-${var.name}-staging"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  lifecycle_rule {
    condition {
      age = var.staging_retention_days
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_service_account" "this" {
  project      = var.project_id
  account_id   = var.name
  display_name = var.name
}

resource "google_storage_bucket_iam_member" "service" {
  bucket = google_storage_bucket.staging.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.this.email}"
}

resource "google_storage_bucket_iam_member" "callers" {
  for_each = toset(var.invoker_service_account_emails)
  bucket   = google_storage_bucket.staging.name
  role     = "roles/storage.objectAdmin"
  member   = "serviceAccount:${each.value}"
}

resource "google_cloud_run_v2_service" "this" {
  project  = var.project_id
  name     = var.name
  location = var.region
  # Reachable only with an ID token from an invoker below.
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.this.email
    timeout         = "${var.timeout_seconds}s"

    # One conversion per instance: it needs the instance's memory, and the
    # app serializes requests anyway.
    max_instance_request_concurrency = 1

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instances
    }

    containers {
      image = var.initial_image

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        # CPU only while a request is in flight.
        cpu_idle          = true
        startup_cpu_boost = true
      }
    }
  }

  lifecycle {
    # Deploys (bin/deploy-docling-service) own the image and revision metadata.
    ignore_changes = [
      template[0].containers[0].image,
      template[0].revision,
      client,
      client_version,
    ]
  }

  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service_iam_member" "invokers" {
  for_each = toset(var.invoker_service_account_emails)
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.this.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${each.value}"
}

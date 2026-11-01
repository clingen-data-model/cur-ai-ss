# PDF parsing on a GPU: docling-serve on Cloud Run.
#
# The worker's PDF Parsing step runs Docling's layout, table-structure and
# OCR models, which take the CPU-only dev-caa VM up to 15 minutes for a long
# supplement. This stack stands up docling-serve (the Docling project's own
# HTTP server around the same converter) on a Cloud Run service with one
# NVIDIA L4, scaling to zero between papers. Everything else in the parse --
# cropping tables and figures, the word layout (docling-parse), table
# correction, anchoring -- stays with the worker; only the converter call
# moves (lib/misc/pdf/remote.py).
#
# The image is docling-serve's own CUDA build, pulled from ghcr.io through
# an Artifact Registry remote repository because Cloud Run deploys only from
# Artifact Registry or Docker Hub. The tag is pinned to the release that
# bundles the docling version pyproject pins, so the server runs the same
# models as the worker would: see var.docling_serve_version.

terraform {
  required_version = ">= 1.5.0"

  backend "gcs" {
    bucket = "caa-terraform-state"
    prefix = "parsing"
  }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = "clingen-caa"
  region  = "us-east4"
}

data "google_project" "project" {}

# Outputs of the dev stack (infrastructure/terraform/dev). This stack needs
# one of them, the dev-caa VM's service account: the worker runs as it, so
# it is what gets to invoke the service and use the exchange bucket below.
data "terraform_remote_state" "dev" {
  backend = "gcs"
  config = {
    bucket = "caa-terraform-state"
    prefix = "dev"
  }
}

locals {
  region = "us-east4"
  image  = "${local.region}-docker.pkg.dev/${data.google_project.project.project_id}/${google_artifact_registry_repository.ghcr.repository_id}/docling-project/docling-serve-cu128:${var.docling_serve_version}"
}

# --- Image: ghcr.io, proxied ---------------------------------------------

resource "google_artifact_registry_repository" "ghcr" {
  location      = local.region
  repository_id = "ghcr"
  format        = "DOCKER"
  mode          = "REMOTE_REPOSITORY"
  description   = "Pull-through cache of ghcr.io (docling-serve images for Cloud Run)"

  remote_repository_config {
    common_repository {
      uri = "https://ghcr.io"
    }
  }
}

# --- Service -------------------------------------------------------------

# Runs with no permissions of its own: the service reads the PDF it is sent
# and answers with the parsed document.
resource "google_service_account" "docling" {
  account_id   = "docling-serve"
  display_name = "docling-serve (Cloud Run)"
}

resource "google_cloud_run_v2_service" "docling" {
  name                = "docling-serve"
  location            = local.region
  ingress             = "INGRESS_TRAFFIC_ALL" # reachable from the VM; callers still need run.invoker
  deletion_protection = false

  # The API reads back a service-level scaling block (zeros) this config
  # never set; without this every plan wants to remove it and rolls a new
  # revision for nothing. Instance bounds are in template.scaling.
  lifecycle {
    ignore_changes = [scaling]
  }

  template {
    service_account                  = google_service_account.docling.email
    timeout                          = "3600s" # Cloud Run's maximum; a 44-page supplement is minutes on an L4
    max_instance_request_concurrency = var.concurrency
    execution_environment            = "EXECUTION_ENVIRONMENT_GEN2"
    gpu_zonal_redundancy_disabled    = true # best-effort failover is enough for a batch step, at ~half the GPU price

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instances
    }

    node_selector {
      accelerator = "nvidia-l4"
    }

    containers {
      image = local.image

      ports {
        container_port = 5001 # docling-serve's default (UVICORN_PORT)
      }

      resources {
        # Cloud Run's recommended shape for one L4 (minimum is 4 CPU / 16Gi).
        limits = {
          cpu              = "8"
          memory           = "32Gi"
          "nvidia.com/gpu" = "1"
        }
        cpu_idle          = false # instance-based billing, required with a GPU
        startup_cpu_boost = true
      }

      env {
        name  = "DOCLING_SERVE_ENABLE_UI"
        value = "false"
      }
      env {
        # One conversion at a time on the one GPU; matched by
        # max_instance_request_concurrency above.
        name  = "DOCLING_SERVE_ENG_LOC_NUM_WORKERS"
        value = tostring(var.concurrency)
      }
      env {
        # How long a sync request waits for its conversion; the default,
        # 120 s, is shorter than a long supplement.
        name  = "DOCLING_SERVE_MAX_SYNC_WAIT"
        value = "3600"
      }
      env {
        name  = "DOCLING_SERVE_LOAD_MODELS_AT_BOOT"
        value = "true"
      }
      env {
        # Figure crops are requested at IMAGE_RESOLUTION_SCALE
        # (lib/misc/pdf/parse.py); the server caps the request at 2.0 unless told otherwise.
        name  = "DOCLING_SERVE_MAX_IMAGES_SCALE"
        value = "4.0"
      }

      # The image is several GB and loads the models at boot: give a cold
      # start up to 30 minutes before the revision is declared unhealthy.
      startup_probe {
        http_get {
          path = "/health"
          port = 5001
        }
        initial_delay_seconds = 10
        period_seconds        = 5
        timeout_seconds       = 5
        failure_threshold     = 360
      }
    }
  }
}

# --- Who may call it -----------------------------------------------------

resource "google_cloud_run_v2_service_iam_member" "worker" {
  name     = google_cloud_run_v2_service.docling.name
  location = google_cloud_run_v2_service.docling.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${data.terraform_remote_state.dev.outputs.service_account_email}"
}

resource "google_cloud_run_v2_service_iam_member" "operators" {
  for_each = toset(var.invokers)
  name     = google_cloud_run_v2_service.docling.name
  location = google_cloud_run_v2_service.docling.location
  role     = "roles/run.invoker"
  member   = each.value
}

# --- Exchange bucket -------------------------------------------------------
#
# Where the worker and the service pass a paper's files. A PDF goes in the
# request body today; through the bucket the worker uploads it and hands
# docling-serve a signed URL (``/v1/convert/source``, ``http_sources``),
# which lifts Cloud Run's 32 MB HTTP/1 body limit and lets the service write
# a result bundle back to a signed URL instead of holding the response open.
# Objects are transient: a day's lifetime, then deleted. Nothing here is the
# copy of record; that stays in the VM's documents/ directory.

resource "google_storage_bucket" "exchange" {
  name                        = "${data.google_project.project.project_id}-parsing-exchange"
  location                    = local.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true # transient objects only

  lifecycle_rule {
    condition {
      age = 1 # days
    }
    action {
      type = "Delete"
    }
  }
}

# The worker reads and writes objects as the VM's service account...
resource "google_storage_bucket_iam_member" "worker" {
  bucket = google_storage_bucket.exchange.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${data.terraform_remote_state.dev.outputs.service_account_email}"
}

# ...and signs the URLs it hands the service with that account's own
# identity. Without a key file, V4 signing goes through the IAM signBlob
# API, which an account may call on itself only with this role.
resource "google_service_account_iam_member" "worker_signs_as_itself" {
  service_account_id = "projects/${data.google_project.project.project_id}/serviceAccounts/${data.terraform_remote_state.dev.outputs.service_account_email}"
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${data.terraform_remote_state.dev.outputs.service_account_email}"
}

# The service needs no grant: it only ever sees signed URLs.

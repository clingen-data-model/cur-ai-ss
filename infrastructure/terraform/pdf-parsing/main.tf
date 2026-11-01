# The PDF parsing service: Docling on a Cloud Run GPU.
#
# The worker's PDF Parsing step runs Docling's layout, table-structure and
# OCR models, which take the CPU-only dev-caa VM up to 15 minutes for a long
# supplement. This stack stands up a PDF parsing service on Cloud Run with
# one NVIDIA L4, scaling to zero between papers: docling-serve, the Docling
# project's own HTTP server around the same converter. Everything else in the parse --
# cropping tables and figures, the word layout (docling-parse), table
# correction, anchoring -- stays with the worker; only the converter call
# moves (lib/misc/pdf/remote.py).
#
# The image is docling-serve's own CUDA build plus the worker's layout
# override (infrastructure/pdf-parsing/Dockerfile). A push to main that
# touches the image's inputs has GitHub Actions
# (.github/workflows/pdf-parsing-image.yml) build it with Cloud Build into
# this stack's repository, from the ghcr.io release pulled through an
# Artifact Registry remote repository (Cloud Run deploys only from Artifact
# Registry or Docker Hub), and roll the service onto it. Terraform creates
# the service on the stock base image and ignores the image after that, so
# a fresh stack comes up without a build and the next workflow run (a push
# to main touching the inputs, or a manual dispatch) puts the override in
# place. The base release, infrastructure/pdf-parsing/base-tag, is the one
# that bundles the docling version pyproject pins, so the server runs the
# same models as the worker would.

terraform {
  required_version = ">= 1.5.0"

  backend "gcs" {
    bucket = "caa-terraform-state"
    prefix = "pdf-parsing"
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
  region   = "us-east4"
  registry = "${local.region}-docker.pkg.dev/${data.google_project.project.project_id}"
  base_tag = trimspace(file("${path.module}/../../pdf-parsing/base-tag"))
  # What the service is created on; see the lifecycle block on the service.
  bootstrap_image = "${local.registry}/${google_artifact_registry_repository.ghcr.repository_id}/docling-project/docling-serve-cu128:${local.base_tag}"
}

# --- Image -----------------------------------------------------------------

# The base image's source: ghcr.io, proxied.
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

# The service image, built by bin/build-pdf-parsing-image.
resource "google_artifact_registry_repository" "images" {
  location      = local.region
  repository_id = "pdf-parsing"
  format        = "DOCKER"
  description   = "The pdf-parsing service image: docling-serve plus the layout override"
}

# Builds run as this account, from GitHub Actions through workload identity
# federation (no key, no secret: GitHub's OIDC token for a run on this
# repository is exchanged for this account's credentials) or by an operator
# with bin/build-pdf-parsing-image. It submits the build, and the build
# itself pulls the base image from the proxy, pushes the result and writes
# its logs; then it rolls the service onto the new image.
resource "google_service_account" "builder" {
  account_id   = "pdf-parsing-builder"
  display_name = "pdf-parsing image builds"
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub Actions OIDC"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  # Only this repository's runs may exchange a token at all.
  attribute_condition = "assertion.repository == \"${var.github_repository}\""
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# ...and only runs on its main branch may act as the builder.
resource "google_service_account_iam_member" "github_builds" {
  service_account_id = google_service_account.builder.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.ref/refs/heads/main"
}

# Submitting a build: the right to create builds, a bucket to stage the
# build context in (gcloud uploads it there; the build reads it back), and
# the right to run the build as the builder account itself.
resource "google_project_iam_member" "builder_submits" {
  project = data.google_project.project.project_id
  role    = "roles/cloudbuild.builds.editor"
  member  = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_storage_bucket" "build_source" {
  name                        = "${data.google_project.project.project_id}-pdf-parsing-build"
  location                    = local.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  lifecycle_rule {
    condition {
      age = 1 # days
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket_iam_member" "builder_stages" {
  bucket = google_storage_bucket.build_source.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_service_account_iam_member" "builder_runs_as_itself" {
  service_account_id = google_service_account.builder.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.builder.email}"
}

# Rolling the service onto the new image: update the service, and act as
# the account it runs as.
resource "google_cloud_run_v2_service_iam_member" "builder_deploys" {
  name     = google_cloud_run_v2_service.pdf_parsing.name
  location = google_cloud_run_v2_service.pdf_parsing.location
  role     = "roles/run.developer"
  member   = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_service_account_iam_member" "builder_deploys_as_service" {
  service_account_id = google_service_account.pdf_parsing.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_artifact_registry_repository_iam_member" "builder_pulls_base" {
  location   = google_artifact_registry_repository.ghcr.location
  repository = google_artifact_registry_repository.ghcr.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_artifact_registry_repository_iam_member" "builder_pushes" {
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_project_iam_member" "builder_logs" {
  project = data.google_project.project.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_service_account_iam_member" "operators_build" {
  for_each           = toset(var.invokers)
  service_account_id = google_service_account.builder.name
  role               = "roles/iam.serviceAccountUser"
  member             = each.value
}

# --- Service -------------------------------------------------------------

# Runs with no permissions of its own: the service reads the PDF it is sent
# and answers with the parsed document.
resource "google_service_account" "pdf_parsing" {
  account_id   = "pdf-parsing"
  display_name = "pdf-parsing (Cloud Run)"
}

resource "google_cloud_run_v2_service" "pdf_parsing" {
  name                = "pdf-parsing"
  location            = local.region
  ingress             = "INGRESS_TRAFFIC_ALL" # reachable from the VM; callers still need run.invoker
  deletion_protection = false

  lifecycle {
    ignore_changes = [
      # The API reads back a service-level scaling block (zeros) this
      # config never set; without this every plan wants to remove it and
      # rolls a new revision for nothing. Instance bounds are in
      # template.scaling.
      scaling,
      # The image is rolled by the build workflow; the service is only
      # created on local.bootstrap_image.
      template[0].containers[0].image,
    ]
  }

  template {
    service_account                  = google_service_account.pdf_parsing.email
    timeout                          = "360s" # the sync wait below, plus upload and response
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
      image = local.bootstrap_image

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
        # 120 s, is shorter than a long supplement. A 32-page paper took 32 s.
        name  = "DOCLING_SERVE_MAX_SYNC_WAIT"
        value = "300"
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
  name     = google_cloud_run_v2_service.pdf_parsing.name
  location = google_cloud_run_v2_service.pdf_parsing.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${data.terraform_remote_state.dev.outputs.service_account_email}"
}

resource "google_cloud_run_v2_service_iam_member" "operators" {
  for_each = toset(var.invokers)
  name     = google_cloud_run_v2_service.pdf_parsing.name
  location = google_cloud_run_v2_service.pdf_parsing.location
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
  name                        = "${data.google_project.project.project_id}-pdf-parsing-exchange"
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

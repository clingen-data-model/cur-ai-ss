# Reserved static IP address
resource "google_compute_address" "this" {
  name         = var.name
  region       = "us-east4"
  network_tier = "PREMIUM"
}

# Service Account for the VM
resource "google_service_account" "this" {
  account_id   = var.name
  display_name = var.name
}

# Compute Instance
resource "google_compute_instance" "this" {
  name         = var.name
  machine_type = var.machine_type
  zone         = var.zone

  tags = var.tags

  boot_disk {
    auto_delete = true
    device_name = var.name

    initialize_params {
      size  = var.boot_disk_size_gb
      type  = var.boot_disk_type
      image = var.boot_image
    }
  }

  network_interface {
    network    = var.network_self_link
    subnetwork = var.subnetwork_self_link

    access_config {
      nat_ip       = google_compute_address.this.address
      network_tier = "PREMIUM"
    }

    nic_type   = "GVNIC"
    stack_type = "IPV4_ONLY"
  }

  service_account {
    email  = google_service_account.this.email
    scopes = ["cloud-platform"]
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    preemptible         = false
    provisioning_model  = "STANDARD"
  }

  shielded_instance_config {
    enable_integrity_monitoring = true
    enable_secure_boot          = false
    enable_vtpm                 = true
  }

  key_revocation_action_type = "NONE"
  allow_stopping_for_update  = true

  metadata = {}

  lifecycle {
    ignore_changes = [
      metadata["ssh-keys"]
    ]
  }
}

# IAM bindings for GCS bucket access
resource "google_storage_bucket_iam_member" "static_resources_read" {
  bucket = "caa-static-resources"
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.this.email}"
}

resource "google_storage_bucket_iam_member" "static_resources_write" {
  bucket = "caa-static-resources"
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.this.email}"
}

# Project-level GCS permission for bucket discovery and administration
resource "google_project_iam_member" "storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.this.email}"
}

# Allow the VM service account to sign blobs (for GCS signed URLs)
resource "google_service_account_iam_member" "token_creator" {
  service_account_id = google_service_account.this.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.this.email}"
}

# --- certbot / Let's Encrypt secret containers ---
# Terraform owns the secret CONTAINERS only; secret VALUES are never stored in TF state.
#  - The Porkbun key/secret values are added out-of-band via `gcloud secrets versions add`
#    (fetched controller-side by the playbook using the operator's creds, so the VM SA
#    needs no IAM on them).
#  - The lineage-cache versions are written at runtime by the VM-side backup deploy-hook,
#    which authenticates as this SA — hence the two IAM grants below, scoped to that one
#    secret (secretVersionAdder to push, secretAccessor to read back for restore/debug).

resource "google_secret_manager_secret" "porkbun_api_key" {
  project   = var.project_id
  secret_id = "caa-certbot-porkbun-api-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "porkbun_secret_key" {
  project   = var.project_id
  secret_id = "caa-certbot-porkbun-secret-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "certbot_archive" {
  project   = var.project_id
  secret_id = "caa-certbot-le-archive"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "certbot_archive_writer" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.certbot_archive.secret_id
  role      = "roles/secretmanager.secretVersionAdder"
  member    = "serviceAccount:${google_service_account.this.email}"
}

resource "google_secret_manager_secret_iam_member" "certbot_archive_reader" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.certbot_archive.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.this.email}"
}

# Reserved static IP address
resource "google_compute_address" "caa_dashboard" {
  name         = "caa-dashboard"
  region       = "us-east4"
  network_tier = "PREMIUM"
}

# Service Account for the VM
resource "google_service_account" "caa_dashboard" {
  account_id   = "caa-dashboard"
  display_name = "caa-dashboard"
}

# IAM role for the service account
resource "google_project_iam_member" "caa_dashboard_storage" {
  project = "clingen-caa"
  role    = "roles/storage.objectUser"
  member  = "serviceAccount:${google_service_account.caa_dashboard.email}"
}

# Compute Instance
resource "google_compute_instance" "caa_dashboard" {
  name         = "caa-dashboard"
  machine_type = "c4a-standard-2"
  zone         = "us-east4-a"

  tags = ["http-server", "https-server", "lb-health-check"]

  boot_disk {
    auto_delete = true
    device_name = "caa-dashboard"

    initialize_params {
      size  = 100
      type  = "hyperdisk-balanced"
      image = "ubuntu-os-cloud/ubuntu-2510-arm64"
    }
  }

  network_interface {
    network    = google_compute_network.default.id
    subnetwork = google_compute_subnetwork.default.id

    access_config {
      nat_ip       = google_compute_address.caa_dashboard.address
      network_tier = "PREMIUM"
    }

    nic_type   = "GVNIC"
    stack_type = "IPV4_ONLY"
  }

  service_account {
    email  = google_service_account.caa_dashboard.email
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

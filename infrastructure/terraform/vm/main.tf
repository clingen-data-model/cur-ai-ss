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

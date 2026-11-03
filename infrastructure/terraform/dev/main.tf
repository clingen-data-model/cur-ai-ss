terraform {
  required_version = ">= 1.5.0"

  backend "gcs" {
    bucket = "caa-terraform-state"
    prefix = "dev"
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
  zone    = "us-east4-a"
}

data "google_project" "project" {}
data "terraform_remote_state" "shared_network" {
  backend = "gcs"
  config = {
    bucket = "caa-terraform-state"
    prefix = "shared"
  }
}

# Replacing the machine (2026-11: c4a-standard-2 on hyperdisk, Arm, sized for
# running Docling's models in the worker, to e2-medium on pd-balanced, x86,
# now that PDF parsing is on the Cloud Run service; about $100 to $35 a month).
# The address, service account and secrets stay; only the instance changes,
# in three steps, so the old machine serves until the new one is loaded:
#
#   1. Add `standby` below and apply: the new instance comes up beside the old
#      with an ephemeral address. Run the playbook against it through IAP
#      (README, Deployment), copy /var/caa across, check the site on it.
#   2. Cut over by hand: stop the services on the old machine, copy the last
#      changes, move the static address --
#        gcloud compute instances delete-access-config dev-caa \
#          --access-config-name external-nat --zone us-east4-a
#        gcloud compute instances add-access-config <standby name> \
#          --address 34.86.179.79 --zone us-east4-a
#      -- and check the site. Stop the old machine; it is the fallback.
#   3. Make the standby the instance: set `instance_name` and the machine
#      variables below to the standby's, drop `standby`, and move the state --
#        terraform state rm module.dev-caa.google_compute_instance.this
#        terraform state mv 'module.dev-caa.google_compute_instance.standby[0]' \
#          module.dev-caa.google_compute_instance.this
#      -- then plan (nothing to change) and delete the old machine with
#      gcloud when it has not been needed for a while.
module "dev-caa" {
  source               = "../vm"
  project_id           = data.google_project.project.project_id
  name                 = "dev-caa"
  network_self_link    = data.terraform_remote_state.shared_network.outputs.network.self_link
  subnetwork_self_link = data.terraform_remote_state.shared_network.outputs.subnetwork.self_link

  # The machine since the 2026-11 replacement (step 3 above): the address,
  # service account and secrets are still named dev-caa.
  instance_name     = "dev-caa-2"
  machine_type      = "e2-medium"
  boot_disk_type    = "pd-balanced"
  boot_disk_size_gb = 100
  boot_image        = "ubuntu-os-cloud/ubuntu-2404-lts-amd64"
}

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
    bucket = "terraform-state"
    prefix = "shared"
  }
}

module "dev-caa" {
  source                    = "../vm"
  project_id                = data.google_project.project.project_id
  name                      = "dev-caa"
  network_self_link         = data.terraform_remote_state.shared_network.outputs.network.self_link
  subnetwork_self_link      = data.terraform_remote_state.shared_network.outputs.subnetwork.self_link
}

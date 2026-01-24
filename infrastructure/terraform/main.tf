terraform {
  required_version = ">= 1.5.0"

  backend "gcs" {
    bucket = "clingen-caa-terraform-state"
    prefix = "cur-ai-ss"
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

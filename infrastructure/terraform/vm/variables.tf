variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "name" {
  type        = string
  description = "Base name for all caa dashboard resources"
}

variable "zone" {
  type        = string
  description = "GCP zone in us-east4"
  default     = "us-east4-a"
}

variable "machine_type" {
  type        = string
  default     = "c4a-standard-2"
}

variable "boot_disk_size_gb" {
  type    = number
  default = 100
}

variable "boot_disk_type" {
  type    = string
  default = "hyperdisk-balanced"
}

variable "boot_image" {
  type    = string
  default = "ubuntu-os-cloud/ubuntu-2510-arm64"
}

variable "tags" {
  type    = list(string)
  default = ["http-server", "https-server", "lb-health-check"]
}

variable "network_self_link" {
  description = "Self-link of the VPC network (required for Shared VPC or cross-project usage)"
  type        = string
}

variable "subnetwork_self_link" {
  description = "Self-link of the subnetwork"
  type        = string
}

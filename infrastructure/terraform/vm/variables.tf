variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "name" {
  type        = string
  description = "Base name for all caa dashboard resources"
}

variable "instance_name" {
  type        = string
  default     = null
  description = <<-EOT
    The instance's own name when it is not var.name. The address, the service
    account and the secrets keep var.name whatever the instance is called,
    which is what lets a replacement machine take over from the one before
    it without touching IAM or DNS (see `standby`).
  EOT
}

variable "standby" {
  description = <<-EOT
    A second instance beside the first, on the same service account and
    subnet with an ephemeral address: the next machine, built and loaded
    while the first still serves, before the static address moves over and
    the first is retired. null for none. The sequence is in
    infrastructure/terraform/dev/main.tf.
  EOT
  type = object({
    name              = string
    machine_type      = string
    boot_disk_type    = string
    boot_disk_size_gb = number
    boot_image        = string
  })
  default = null
}

variable "zone" {
  type        = string
  description = "GCP zone in us-east4"
  default     = "us-east4-a"
}

variable "machine_type" {
  type    = string
  default = "c4a-standard-2"
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
  default = "ubuntu-os-cloud/ubuntu-2404-lts-arm64"
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

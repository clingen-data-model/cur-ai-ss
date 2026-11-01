variable "docling_serve_version" {
  type        = string
  description = <<-EOT
    docling-serve release tag. Each release bundles one docling version (listed
    in its GitHub release notes); keep this on the release that bundles the
    docling pinned in pyproject.toml so the service runs the same models the
    worker would. v1.23.0 is docling 2.82.0. Only some releases have a cu128
    image: check the tag exists before bumping.
  EOT
  default     = "v1.23.0"
}

variable "max_instances" {
  type        = number
  description = "Upper bound on L4 instances. A new project's automatic Cloud Run GPU quota in a region is 3."
  default     = 1
}

variable "concurrency" {
  type        = number
  description = <<-EOT
    Conversions one instance runs at once, sharing its GPU. Two overlap well:
    a conversion spends much of its time on CPU phases (page rendering, OCR
    preprocessing, assembly) with the GPU idle, the models are small next to
    the L4's 24 GB, and two long documents' page renders fit in 32 GiB. The
    worker only benefits once its own PDF Parsing cap (TASK_CONCURRENCY in
    lib/bin/worker.py, 1 while Docling ran on the VM) is raised to match.
  EOT
  default     = 2
}

variable "invokers" {
  type        = list(string)
  description = "IAM members besides the VM allowed to call the service, for testing from a laptop (`gcloud auth print-identity-token`)."
  default     = ["user:bblanken@broadinstitute.org"]
}

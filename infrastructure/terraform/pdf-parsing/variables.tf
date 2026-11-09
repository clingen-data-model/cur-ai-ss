variable "github_repository" {
  type        = string
  description = "The GitHub repository whose Actions runs on main may build and roll the image."
  default     = "clingen-data-model/cur-ai-ss"
}

variable "max_instances" {
  type        = number
  description = <<-EOT
    Upper bound on L4 instances. A new project's automatic Cloud Run GPU quota
    in a region is 3. Two since 2026-11-09, for the four worker processes each
    holding one parse open (infrastructure/ansible, worker_count): two
    instances at var.concurrency each is room for all four.
  EOT
  default     = 2
}

variable "concurrency" {
  type        = number
  description = <<-EOT
    Conversions one instance runs at once, sharing its GPU. Two overlap well:
    a conversion spends much of its time on CPU phases (page rendering, OCR
    preprocessing, assembly) with the GPU idle, the models are small next to
    the L4's 24 GB, and two long documents' page renders fit in 32 GiB. The
    worker side holds one parse open per worker process (TASK_CONCURRENCY in
    lib/bin/worker.py), so this times var.max_instances is what the workers
    together may have in flight.
  EOT
  default     = 2
}

variable "invokers" {
  type        = list(string)
  description = "IAM members besides the VM allowed to call the service, for testing from a laptop (`gcloud auth print-identity-token`)."
  default     = ["user:bblanken@broadinstitute.org"]
}

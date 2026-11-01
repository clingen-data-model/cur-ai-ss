variable "github_repository" {
  type        = string
  description = "The GitHub repository whose Actions runs on main may build and roll the image."
  default     = "clingen-data-model/cur-ai-ss"
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

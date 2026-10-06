variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "name" {
  type        = string
  description = "Base name for all docling service resources"
  default     = "docling-service"
}

variable "region" {
  type    = string
  default = "us-east4"
}

variable "invoker_service_account_emails" {
  type        = list(string)
  description = "Service accounts allowed to call the service and to read/write its staging bucket (the worker's)"
}

variable "initial_image" {
  type        = string
  description = "Image used only to create the service; deploys replace it (see lifecycle.ignore_changes) and bin/deploy-docling-service pushes the real one"
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "cpu" {
  type    = string
  default = "4"
}

variable "memory" {
  type        = string
  description = "Cloud Run's filesystem is memory, so this must cover the models, the conversion and the result files"
  default     = "16Gi"
}

variable "max_instances" {
  type        = number
  description = "Caps cost and concurrent conversions; the worker runs PDF parsing one at a time anyway"
  default     = 3
}

variable "timeout_seconds" {
  type    = number
  default = 3600
}

variable "staging_retention_days" {
  type    = number
  default = 1
}

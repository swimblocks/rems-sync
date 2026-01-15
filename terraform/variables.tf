variable "project_id" {
  description = "The GCP project ID to deploy the resources to."
  type        = string
}

variable "region" {
  description = "The GCP region to deploy the resources to."
  type        = string
  default     = "us-central1"
}

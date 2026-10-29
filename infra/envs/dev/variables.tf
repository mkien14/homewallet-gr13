variable "worker_image_tag" {
  description = "ECR image tag containing jobs.worker"
  type        = string
}

variable "gemini_model" {
  description = "Gemini model verified by the backend team"
  type        = string
}

variable "api_image_tag" {
  description = "Backend image tag used by the API and migration task"
  type        = string
  default     = "v0.4"
}
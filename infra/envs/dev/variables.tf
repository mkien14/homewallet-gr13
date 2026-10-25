variable "worker_image_tag" {
  description = "ECR image tag containing jobs.worker"
  type        = string
}

variable "gemini_model" {
  description = "Gemini model verified by the backend team"
  type        = string
}
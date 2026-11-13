variable "name" {
  type = string
}
variable "production" {
  type    = bool
  default = false
}

variable "preserve_tagged_images" {
  description = "Keep release digests available for task restarts and controlled rollback."
  type        = bool
  default     = false
}

resource "aws_ecr_repository" "this" {
  name                 = var.name
  image_tag_mutability = (var.production || var.preserve_tagged_images) ? "IMMUTABLE" : "MUTABLE"
  force_delete         = !(var.production || var.preserve_tagged_images)

  image_scanning_configuration {
    scan_on_push = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name
  policy = (var.production || var.preserve_tagged_images) ? jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire only untagged images; keep tagged release artifacts"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.production ? 30 : 14
        }
        action = { type = "expire" }
      }
    ]
    }) : jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the current dev image tag"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["dev"]
          countType     = "imageCountMoreThan"
          countNumber   = 1
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep the 10 most recently pushed images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}

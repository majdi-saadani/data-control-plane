# Container registry for the API image. force_delete lets `terraform destroy` remove it with its images.

resource "aws_ecr_repository" "this" {
  name                 = var.repository_name
  image_tag_mutability = "MUTABLE" # the CI re-points the `latest` tag on every deploy
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Keep storage (and its cost) bounded
resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the last ${var.keep_last_images} images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = var.keep_last_images
      }
      action = { type = "expire" }
    }]
  })
}

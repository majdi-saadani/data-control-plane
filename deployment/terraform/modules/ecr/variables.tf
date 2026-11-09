variable "repository_name" {
  description = "ECR repository name"
  type        = string
}

variable "keep_last_images" {
  description = "Number of images kept by the lifecycle policy"
  type        = number
  default     = 5
}

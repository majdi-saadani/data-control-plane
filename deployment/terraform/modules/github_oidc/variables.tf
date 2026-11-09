variable "role_name" {
  description = "Name of the deploy role assumed by GitHub Actions"
  type        = string
}

variable "github_repository" {
  description = "GitHub repository allowed to assume the role, as owner/name"
  type        = string
}

variable "branches" {
  description = "Branches whose workflows may assume the role"
  type        = list(string)
  default     = ["develop", "main"]
}

variable "create_oidc_provider" {
  description = "Create the GitHub OIDC provider (false if the account already has one)"
  type        = bool
  default     = true
}

variable "existing_oidc_provider_arn" {
  description = "ARN of the existing GitHub OIDC provider when create_oidc_provider = false"
  type        = string
  default     = null
}

variable "ecr_repository_arn" {
  description = "ECR repository the workflow may push to"
  type        = string
}

variable "ecs_service_arn" {
  description = "ECS service the workflow may redeploy"
  type        = string
}

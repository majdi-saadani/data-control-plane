variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-1"
}

variable "env" {
  description = "Environment suffix used in every resource name"
  type        = string
  default     = "dev"
}

variable "allowed_cidrs" {
  description = "CIDR blocks allowed to reach the API, e.g. [\"203.0.113.10/32\"] (your public IP)"
  type        = list(string)
}

variable "databricks_host" {
  description = "Databricks workspace URL (https://dbc-xxxx.cloud.databricks.com); empty = Databricks disabled"
  type        = string
  default     = ""
}

variable "databricks_token" {
  description = "Databricks personal access token, stored in SSM Parameter Store (SecureString). Set via TF_VAR_databricks_token."
  type        = string
  default     = ""
  sensitive   = true
}

variable "api_image_tag" {
  description = "Image tag deployed by the ECS task definition (the CI re-points `latest`)"
  type        = string
  default     = "latest"
}

variable "api_desired_count" {
  description = "Number of API tasks; set 0 to pause the API without destroying the stack"
  type        = number
  default     = 1
}

variable "use_fargate_spot" {
  description = "Run the API on Fargate Spot (cheaper, may be interrupted)"
  type        = bool
  default     = true
}

variable "github_repository" {
  description = "GitHub repository allowed to deploy, as owner/name"
  type        = string
  default     = "majdi-saadani/data-control-plane"
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub OIDC provider in this account (false if it already exists)"
  type        = bool
  default     = true
}

variable "existing_github_oidc_provider_arn" {
  description = "ARN of the existing GitHub OIDC provider when create_github_oidc_provider = false"
  type        = string
  default     = null
}

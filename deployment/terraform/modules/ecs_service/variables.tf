variable "aws_region" {
  description = "Region (for the awslogs driver)"
  type        = string
}

variable "cluster_name" {
  description = "ECS cluster name"
  type        = string
}

variable "service_name" {
  description = "ECS service / task family name"
  type        = string
}

variable "container_name" {
  description = "Container name inside the task definition"
  type        = string
  default     = "api"
}

variable "container_image" {
  description = "Full image reference (ECR URL + tag)"
  type        = string
}

variable "container_port" {
  description = "Port exposed by the container"
  type        = number
  default     = 8000
}

variable "cpu" {
  description = "Task CPU units (256 = 0.25 vCPU, the Fargate minimum)"
  type        = number
  default     = 256
}

variable "memory" {
  description = "Task memory in MiB (512 = Fargate minimum for 256 CPU)"
  type        = number
  default     = 512
}

variable "desired_count" {
  description = "Number of tasks (0 pauses the service without destroying anything)"
  type        = number
  default     = 1
}

variable "use_fargate_spot" {
  description = "Run on FARGATE_SPOT (about 70% cheaper, may be interrupted) instead of FARGATE"
  type        = bool
  default     = true
}

variable "vpc_id" {
  description = "VPC hosting the service"
  type        = string
}

variable "subnet_ids" {
  description = "Public subnets for the tasks"
  type        = list(string)
}

variable "allowed_cidrs" {
  description = "CIDR blocks allowed to reach the API (e.g. your IP/32)"
  type        = list(string)
}

variable "environment" {
  description = "Plain environment variables for the container"
  type        = map(string)
  default     = {}
}

variable "secrets" {
  description = "Secret environment variables: name -> SSM parameter ARN"
  type        = map(string)
  default     = {}
}

variable "task_policy_json" {
  description = "IAM policy document (JSON) for the application (task role)"
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 7
}

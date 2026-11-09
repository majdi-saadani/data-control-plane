variable "function_name" {
  description = "Lambda function name"
  type        = string
}

variable "source_file" {
  description = "Path to the single Python file to package (stdlib + runtime boto3 only)"
  type        = string
}

variable "handler" {
  description = "Handler entry point (file.function)"
  type        = string
  default     = "handler.lambda_handler"
}

variable "runtime" {
  description = "Lambda runtime"
  type        = string
  default     = "python3.12"
}

variable "timeout" {
  description = "Function timeout in seconds"
  type        = number
  default     = 30
}

variable "memory_size" {
  description = "Memory in MB"
  type        = number
  default     = 128
}

variable "environment" {
  description = "Environment variables injected into the function"
  type        = map(string)
  default     = {}
}

variable "policy_json" {
  description = "IAM policy document (JSON) granting the function its permissions, per-resource ARNs"
  type        = string
}

variable "kinesis_event_source_arn" {
  description = "ARN of a Kinesis stream to consume from (null = no trigger)"
  type        = string
  default     = null
}

variable "batch_size" {
  description = "Records per invocation when triggered by Kinesis"
  type        = number
  default     = 100
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 7
}

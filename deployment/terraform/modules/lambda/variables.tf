variable "function_name" {
  description = "Lambda function name"
  type        = string
}

variable "kinesis_stream_arn" {
  description = "ARN of the Kinesis stream allowed for reading"
  type        = string
}

variable "source_file" {
  description = "Path to the handler.py file to package"
  type        = string
}
variable "dynamodb_table_arn" {
  description = "ARN of the DynamoDB table allowed for writing"
  type        = string
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name (injected as an env var)"
  type        = string
}

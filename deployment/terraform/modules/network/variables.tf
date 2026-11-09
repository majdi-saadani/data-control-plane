variable "name" {
  description = "Name prefix for the VPC and its components"
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_count" {
  description = "Number of public subnets (one per AZ)"
  type        = number
  default     = 2
}

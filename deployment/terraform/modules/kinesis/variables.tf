variable "stream_name" {
  description = "Kinesis stream name in AWS"
  type        = string
}

variable "shard_count" {
  description = "Number of shards (1 shard = 1 MB/s write throughput)"
  type        = number
  default     = 1
}

variable "retention_hours" {
  description = "Record retention in hours (24 = minimum, free)"
  type        = number
  default     = 24
}
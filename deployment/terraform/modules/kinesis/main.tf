resource "aws_kinesis_stream" "this" {
  name             = var.stream_name
  retention_period = var.retention_hours

  stream_mode_details {
    stream_mode = "PROVISIONED"
  }

  shard_count = var.shard_count
}
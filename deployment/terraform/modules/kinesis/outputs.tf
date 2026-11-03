output "stream_name" {
  value = aws_kinesis_stream.this.name
}

output "stream_arn" {
  value = aws_kinesis_stream.this.arn
}
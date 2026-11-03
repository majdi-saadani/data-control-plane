resource "aws_dynamodb_table" "this" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "sensor_id"
  range_key = "event_timestamp"

  attribute {
    name = "sensor_id"
    type = "S"
  }

  attribute {
    name = "event_timestamp"
    type = "S"
  }
}
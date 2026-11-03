module "energy_stream" {
  source = "../../modules/kinesis"

  stream_name = "energy-sensor-events-dev"
  shard_count = 1
}

module "energy_consumer" {
  source = "../../modules/lambda"

  function_name      = "energy-events-consumer-dev"
  source_file        = "${path.root}/../../../../src/lambda_consumer/handler.py"
  kinesis_stream_arn = module.energy_stream.stream_arn
  dynamodb_table_arn = module.energy_measurements_table.table_arn
  dynamodb_table_name = module.energy_measurements_table.table_name
}

module "energy_measurements_table" {
  source = "../../modules/dynamodb"

  table_name = "energy-measurements-dev"
}
# dev environment: hot path (Kinesis -> Lambda -> DynamoDB) + control plane (ECS API, tracking table,
# event generator Lambda) + CI/CD role. Every resource name carries the `-${var.env}` suffix.

locals {
  src_dir = "${path.root}/../../../../src"
}

# ---------------------------------------------------------------- hot path

module "energy_stream" {
  source = "../../modules/kinesis"

  stream_name = "energy-sensor-events-${var.env}"
  shard_count = 1
}

module "energy_measurements_table" {
  source = "../../modules/dynamodb"

  table_name = "energy-measurements-${var.env}"
  hash_key   = "sensor_id"
  range_key  = "event_timestamp"
  attributes = [
    { name = "sensor_id", type = "S" },
    { name = "event_timestamp", type = "S" },
  ]
}

module "energy_consumer" {
  source = "../../modules/lambda"

  function_name            = "energy-events-consumer-${var.env}"
  source_file              = "${local.src_dir}/lambda_consumer/handler.py"
  kinesis_event_source_arn = module.energy_stream.stream_arn
  batch_size               = 100
  policy_json              = data.aws_iam_policy_document.consumer.json

  environment = {
    TABLE_NAME = module.energy_measurements_table.table_name
  }
}

# ---------------------------------------------------------------- control plane

module "event_generator" {
  source = "../../modules/lambda"

  function_name = "energy-event-generator-${var.env}"
  source_file   = "${local.src_dir}/lambda_event_generator/handler.py"
  timeout       = 60
  policy_json   = data.aws_iam_policy_document.event_generator.json

  environment = {
    STREAM_NAME = module.energy_stream.stream_name
  }
}

module "pipeline_runs_table" {
  source = "../../modules/dynamodb"

  table_name = "energy-pipeline-runs-${var.env}"
  hash_key   = "run_id"
  range_key  = "sk"
  attributes = [
    { name = "run_id", type = "S" },
    { name = "sk", type = "S" },
    { name = "pipeline_name", type = "S" },
    { name = "started_at", type = "S" },
  ]
  global_secondary_indexes = [
    { name = "pipeline_name-started_at-index", hash_key = "pipeline_name", range_key = "started_at" },
  ]
}

module "network" {
  source = "../../modules/network"

  name = "energy-vpc-${var.env}"
}

module "api_registry" {
  source = "../../modules/ecr"

  repository_name = "energy-control-plane-${var.env}"
}

# Databricks token kept out of the task definition: SecureString read by ECS at task start
resource "aws_ssm_parameter" "databricks_token" {
  count = var.databricks_token != "" ? 1 : 0

  name  = "/energy/${var.env}/databricks_token"
  type  = "SecureString"
  value = var.databricks_token
}

module "api" {
  source = "../../modules/ecs_service"

  aws_region       = var.aws_region
  cluster_name     = "energy-control-plane-${var.env}"
  service_name     = "energy-control-plane-api-${var.env}"
  container_image  = "${module.api_registry.repository_url}:${var.api_image_tag}"
  desired_count    = var.api_desired_count
  use_fargate_spot = var.use_fargate_spot

  vpc_id        = module.network.vpc_id
  subnet_ids    = module.network.public_subnet_ids
  allowed_cidrs = var.allowed_cidrs

  task_policy_json = data.aws_iam_policy_document.api_task.json

  environment = {
    LOG_LEVEL             = "INFO"
    AWS_REGION            = var.aws_region
    KINESIS_STREAM_NAME   = module.energy_stream.stream_name
    TRACKING_BACKEND      = "dynamodb"
    TRACKING_TABLE_NAME   = module.pipeline_runs_table.table_name
    PIPELINES_CONFIG_PATH = "config/pipelines.yaml"
    DATABRICKS_HOST       = var.databricks_host
  }

  secrets = var.databricks_token != "" ? { DATABRICKS_TOKEN = aws_ssm_parameter.databricks_token[0].arn } : {}
}

# ---------------------------------------------------------------- CI/CD

module "github_deploy" {
  source = "../../modules/github_oidc"

  role_name                  = "energy-github-deploy-${var.env}"
  github_repository          = var.github_repository
  branches                   = ["develop", "main"]
  create_oidc_provider       = var.create_github_oidc_provider
  existing_oidc_provider_arn = var.existing_github_oidc_provider_arn
  ecr_repository_arn         = module.api_registry.repository_arn
  ecs_service_arn            = module.api.service_arn
}

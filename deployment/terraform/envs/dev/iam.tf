# Least-privilege policies, one per workload, per-resource ARNs only.

# Consumer Lambda: read the stream, write the measurements table
data "aws_iam_policy_document" "consumer" {
  statement {
    actions = [
      "kinesis:GetRecords",
      "kinesis:GetShardIterator",
      "kinesis:DescribeStream",
      "kinesis:ListShards",
    ]
    resources = [module.energy_stream.stream_arn]
  }

  statement {
    actions   = ["dynamodb:PutItem", "dynamodb:BatchWriteItem"]
    resources = [module.energy_measurements_table.table_arn]
  }
}

# Event generator Lambda: publish to the stream
data "aws_iam_policy_document" "event_generator" {
  statement {
    actions   = ["kinesis:PutRecord", "kinesis:PutRecords", "kinesis:DescribeStream"]
    resources = [module.energy_stream.stream_arn]
  }
}

# API task role: tracking table (+ its index), invoke the generator Lambda, publish events
data "aws_iam_policy_document" "api_task" {
  statement {
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:BatchWriteItem",
    ]
    resources = [
      module.pipeline_runs_table.table_arn,
      "${module.pipeline_runs_table.table_arn}/index/*",
    ]
  }

  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [module.event_generator.function_arn]
  }

  statement {
    actions   = ["kinesis:PutRecord", "kinesis:PutRecords", "kinesis:DescribeStream"]
    resources = [module.energy_stream.stream_arn]
  }
}

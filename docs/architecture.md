# Architecture Decision Notes

## 1. Partition key = sensor_id (Kinesis AND DynamoDB)
Per-sensor ordering guarantee end-to-end... trade-off vs random key (better
load spread, no ordering)...

## 2. Kinesis PROVISIONED vs ON_DEMAND
Known low throughput → 1 provisioned shard (~$14/mo) vs on-demand floor (~$32/mo)...

## 3. Deduplication strategy: best-effort in compute, idempotence in storage
Intra-batch dedup in Lambda (cheap), but the real guarantee is the DynamoDB
composite key (sensor_id + event_timestamp): writing twice = same result...

## 4. Poison-pill protection
Per-record try/except: one malformed event is rejected and logged instead of
failing the invocation and blocking the shard in retry loops...

## 5. Validation placement: minimal in hot path, full schema in cold path
Why not Pydantic in the Lambda (packaging weight, latency, cold start) —
schema enforcement belongs to the Databricks batch layer...

## 6. IAM: least privilege, three lessons
Trust policy vs permissions policy vs PassRole. Deployer scoped to
`table/energy-*` name prefix. Known debt: AWSLambda_FullAccess to be replaced...

## 7. Event envelope with call_id
Every record published to Kinesis is `{call_id, type, emitted_at, data}`. `call_id` is the
`X-Request-ID` of the API call (or the Lambda `aws_request_id`, or the pipeline's call_id when the
generator is invoked by the orchestrator), so a stored measurement can be traced back to the call
that produced it. The consumer unwraps `data` and keeps `call_id`/`emitted_at` on the item; it
still accepts legacy top-level records so publisher and consumer deploy independently.

## 8. Orchestration in the API process, not a workflow engine
A run is executed by a FastAPI background task: steps in order, tasks of a parallel step in a
`ThreadPoolExecutor`, Databricks polled every `POLL_INTERVAL_S`. Cheap and simple for one
Fargate task. Known limitation: if the task is replaced mid-run (deploy, Spot interruption) the
run stays `RUNNING` in the table. Step Functions or a separate worker is the upgrade path when
that matters.

## 9. Tracking table: single table, two item kinds
`energy-pipeline-runs-dev`, pk `run_id`, sk `RUN` or `TASK#<step>#<task>`: one query returns a
run with all its tasks. GSI `pipeline_name-started_at-index` lists runs per pipeline, newest first,
and backs the "one active run per pipeline" check (409). On-demand billing: zero idle cost.
Task results are stored as JSON strings (DynamoDB has no float type).

## 10. Databricks jobs referenced by name
Pipelines declare `job_name` (resolved via `jobs/list?name=` at run time) or `job_id`. Names are
what people see in the UI and survive a workspace rebuild; ids are faster and unambiguous.
Success = `life_cycle_state` terminal and `result_state == SUCCESS`; a timeout cancels the run.

## 11. ECS Fargate without ALB or NAT (cost)
Target: < 20 €/month and `terraform destroy` after each session. Fargate Spot 0.25 vCPU with a
public IP in a public subnet; the security group only allows `allowed_cidrs`. An ALB (~16 €) and a
NAT gateway (~32 €) would each exceed the budget alone. `api_desired_count = 0` pauses the API
without destroying. The VPC is created by Terraform so the destroy removes it too.

## 12. CI/CD with OIDC and a mutable `latest` tag
GitHub Actions assumes a Terraform-managed IAM role (scoped to the repo and branches, allowed to
push to one ECR repo and update one ECS service): no AWS keys in GitHub. The task definition points
to `:latest`; the CI pushes `:<sha>` + `:latest` and forces a new deployment, so Terraform state and
the running image never diverge. Trade-off: no image pinning in Terraform (acceptable in dev).

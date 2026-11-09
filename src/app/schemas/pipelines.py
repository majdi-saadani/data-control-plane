"""Request/response schemas for the /pipelines and /runs endpoints."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, field_validator

from app.domain.pipeline import DatabricksJobTask, ExecutionMode, LambdaTask, Pipeline, RunStatus


class TaskDefinition(BaseModel):
    name: str
    type: str
    target: str            # job name/id or Lambda function name


class StepDefinition(BaseModel):
    name: str
    mode: ExecutionMode
    tasks: list[TaskDefinition]


class PipelineDefinition(BaseModel):
    name: str
    description: str
    steps: list[StepDefinition]

    @classmethod
    def from_domain(cls, pipeline: Pipeline) -> PipelineDefinition:
        return cls(
            name=pipeline.name,
            description=pipeline.description,
            steps=[
                StepDefinition(
                    name=step.name,
                    mode=step.mode,
                    tasks=[TaskDefinition(name=task.name, type=task.type, target=_target(task)) for task in step.tasks],
                )
                for step in pipeline.steps
            ],
        )


def _target(task: DatabricksJobTask | LambdaTask) -> str:
    if isinstance(task, LambdaTask):
        return task.function_name
    return str(task.job_id) if task.job_id is not None else (task.job_name or "")


class StartRunResponse(BaseModel):
    run_id: str
    pipeline_name: str
    status: RunStatus
    call_id: str


class TaskRunResponse(BaseModel):
    step_name: str
    task_name: str
    task_type: str
    status: RunStatus
    external_ref: str | None = None
    run_page_url: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None

    @field_validator("result", mode="before")
    @classmethod
    def _decode_result(cls, value: Any) -> Any:
        # Stored as a JSON string in DynamoDB (floats are not natively supported)
        return json.loads(value) if isinstance(value, str) else value


class PipelineRunSummary(BaseModel):
    run_id: str
    pipeline_name: str
    status: RunStatus
    call_id: str
    started_at: str
    finished_at: str | None = None
    current_step: str | None = None
    error: str | None = None


class PipelineRunResponse(PipelineRunSummary):
    tasks: list[TaskRunResponse]

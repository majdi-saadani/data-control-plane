"""Pipeline definitions: what the orchestrator executes.

A pipeline is an ordered list of steps (e.g. generate -> bronze -> silver -> gold).
Steps run one after the other; a step starts only when the previous one succeeded.
Inside a step, tasks run either in parallel or sequentially (`mode`).
Definitions are loaded from a YAML file (see config/pipelines.yaml).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


class ExecutionMode(StrEnum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"   # step not executed because a previous step failed
    TIMEOUT = "TIMEOUT"

    @property
    def is_terminal(self) -> bool:
        return self in {RunStatus.SUCCESS, RunStatus.FAILED, RunStatus.SKIPPED, RunStatus.TIMEOUT}


class DatabricksJobTask(BaseModel):
    """Runs an existing Databricks job, referenced by name or id."""

    type: Literal["databricks_job"] = "databricks_job"
    name: str
    job_name: str | None = Field(default=None, description="Job name as shown in the Databricks UI")
    job_id: int | None = Field(default=None, description="Job id (takes precedence over job_name)")
    parameters: dict[str, str] = Field(default_factory=dict, description="job_parameters passed to run-now")
    timeout_minutes: int | None = None

    @model_validator(mode="after")
    def _job_reference_required(self) -> DatabricksJobTask:
        if self.job_id is None and not self.job_name:
            raise ValueError(f"task '{self.name}': either job_name or job_id is required")
        return self


class LambdaTask(BaseModel):
    """Invokes an AWS Lambda function synchronously and waits for its result."""

    type: Literal["lambda"] = "lambda"
    name: str
    function_name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_minutes: int | None = None


Task = Annotated[DatabricksJobTask | LambdaTask, Field(discriminator="type")]


class Step(BaseModel):
    name: str
    mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    tasks: list[Task] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_task_names(self) -> Step:
        names = [task.name for task in self.tasks]
        if len(names) != len(set(names)):
            raise ValueError(f"step '{self.name}': task names must be unique")
        return self


class Pipeline(BaseModel):
    name: str
    description: str = ""
    steps: list[Step] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_step_names(self) -> Pipeline:
        names = [step.name for step in self.steps]
        if len(names) != len(set(names)):
            raise ValueError(f"pipeline '{self.name}': step names must be unique")
        return self


class PipelinesConfig(BaseModel):
    """Root of the YAML file: `pipelines: {<name>: {...}}`."""

    pipelines: dict[str, Pipeline]

    @model_validator(mode="before")
    @classmethod
    def _inject_names(cls, data: Any) -> Any:
        # Allow `pipelines: {my-pipeline: {steps: [...]}}` without repeating `name`
        if isinstance(data, dict) and isinstance(data.get("pipelines"), dict):
            for name, pipeline in data["pipelines"].items():
                if isinstance(pipeline, dict):
                    pipeline.setdefault("name", name)
        return data

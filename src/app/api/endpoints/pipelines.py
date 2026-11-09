"""/pipelines and /runs endpoints: launch pipelines and follow their execution."""

from fastapi import APIRouter, BackgroundTasks, Query, Request, status

from app.api.dependencies import OrchestratorDep, PipelineRegistryDep
from app.schemas.pipelines import PipelineDefinition, PipelineRunResponse, PipelineRunSummary, StartRunResponse

router = APIRouter(tags=["pipelines"])


@router.get("/pipelines", response_model=list[PipelineDefinition])
def list_pipelines(registry: PipelineRegistryDep) -> list[PipelineDefinition]:
    """Pipelines declared in config/pipelines.yaml."""
    return [PipelineDefinition.from_domain(pipeline) for pipeline in registry.list()]


@router.get("/pipelines/{name}", response_model=PipelineDefinition)
def get_pipeline(name: str, registry: PipelineRegistryDep) -> PipelineDefinition:
    return PipelineDefinition.from_domain(registry.get(name))


@router.post("/pipelines/{name}/run", response_model=StartRunResponse, status_code=status.HTTP_202_ACCEPTED)
def run_pipeline(name: str, request: Request, background: BackgroundTasks,
                 orchestrator: OrchestratorDep) -> StartRunResponse:
    """Start a pipeline run. Returns at once; follow it with GET /runs/{run_id}."""
    call_id = request.state.request_id
    run = orchestrator.start_run(name, call_id=call_id)
    background.add_task(orchestrator.execute_run, run["run_id"], name, call_id)
    return StartRunResponse(**run)


@router.get("/pipelines/{name}/runs", response_model=list[PipelineRunSummary])
def list_runs(name: str, orchestrator: OrchestratorDep,
              limit: int = Query(default=20, ge=1, le=100)) -> list[PipelineRunSummary]:
    """Most recent runs of a pipeline, newest first."""
    return [PipelineRunSummary(**run) for run in orchestrator.list_runs(name, limit)]


@router.get("/runs/{run_id}", response_model=PipelineRunResponse)
def get_run(run_id: str, orchestrator: OrchestratorDep) -> PipelineRunResponse:
    """A run with the status of each of its tasks."""
    return PipelineRunResponse(**orchestrator.get_run(run_id))

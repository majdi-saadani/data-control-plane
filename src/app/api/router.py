"""Single place where routers are registered: add every new endpoint here."""

from fastapi import APIRouter

from app.api.endpoints import databricks, events, health, pipelines

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(events.router)
api_router.include_router(databricks.router)
api_router.include_router(pipelines.router)

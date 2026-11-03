"""FastAPI application entry point.

Run locally (from the repo root):
    uvicorn app.main:app --app-dir src --reload
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.middleware.request_context import RequestContextMiddleware
from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.error("%s: %s", type(exc).__name__, exc.message)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(api_router)
    return app


app = create_app()

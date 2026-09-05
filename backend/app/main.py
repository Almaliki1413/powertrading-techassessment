from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import health
from app.api.problem_details import install_exception_handlers, request_id_for
from app.api.v1 import config as config_routes
from app.api.v1 import datasets as dataset_routes
from app.api.v1 import optimizations as optimization_routes
from app.application.resolve_dataset import ResolveDataset
from app.application.run_benchmark import RunBenchmark
from app.application.validate_day import ValidateDay
from app.infrastructure.aemo.archive_client import ArchiveClient
from app.infrastructure.storage.content_cache import ContentCache
from app.settings import Settings, get_settings

ROOT = Path(__file__).resolve().parents[2]


class StructuredLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Any:
        request_id = request_id_for(request)
        request.state.request_id = request_id
        response = await call_next(request)
        logging.getLogger("nsw1").info(
            json.dumps(
                {
                    "event": "api.completed",
                    "request_id": request_id,
                    "path": request.url.path,
                    "method": request.method,
                    "status": response.status_code,
                }
            )
        )
        response.headers["x-request-id"] = request_id
        response.headers["content-security-policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'"
        )
        return response


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    app = FastAPI(
        title="NSW1 BESS Perfect-Hindsight Benchmark",
        version="1.0.0",
        description="Perfect-hindsight benchmark—not a live trading forecast.",
    )
    app.add_middleware(StructuredLogMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.dev_cors_origin, "http://localhost:5173"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    cache = ContentCache(settings.cache_dir / "normalized")
    client = ArchiveClient(settings)
    resolver = ResolveDataset(settings, cache, client)
    validator = ValidateDay(resolver)
    runner = RunBenchmark(settings, validator)
    app.state.settings = settings
    app.state.resolver = resolver
    app.state.runner = runner

    install_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(config_routes.router, prefix="/api/v1")
    app.include_router(dataset_routes.router, prefix="/api/v1")
    app.include_router(optimization_routes.router, prefix="/api/v1")

    dist = settings.frontend_dist
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", response_model=None)
        async def spa(full_path: str):
            if full_path.startswith("api/") or full_path in {"health", "ready"}:
                return JSONResponse({"code": "NOT_FOUND", "message": "Not found"}, status_code=404)
            index = dist / "index.html"
            candidate = dist / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index)

    return app


app = create_app()

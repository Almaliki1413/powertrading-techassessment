"""RFC7807-style problem details with stable domain codes."""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.errors import DomainError, InvalidConfiguration, InvalidDateRange


def request_id_for(request: Request) -> str:
    existing = request.headers.get("x-request-id")
    if existing:
        return existing
    return str(uuid.uuid4())


def problem_payload(
    *,
    code: str,
    message: str,
    blocking: bool,
    request_id: str,
    details: dict[str, object] | None = None,
    status: int,
) -> dict[str, object]:
    return {
        "code": code,
        "message": message,
        "blocking": blocking,
        "request_id": request_id,
        "details": details or {},
        "status": status,
    }


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        payload = problem_payload(
            code=exc.code,
            message=exc.message,
            blocking=exc.blocking,
            request_id=request_id_for(request),
            details=exc.details,
            status=exc.http_status,
        )
        return JSONResponse(status_code=exc.http_status, content=payload)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        payload = problem_payload(
            code=InvalidDateRange.code
            if any("date" in str(err.get("loc", "")).lower() for err in exc.errors())
            else InvalidConfiguration.code,
            message="Request validation failed",
            blocking=True,
            request_id=request_id_for(request),
            details={"errors": exc.errors()},
            status=422,
        )
        return JSONResponse(status_code=422, content=payload)

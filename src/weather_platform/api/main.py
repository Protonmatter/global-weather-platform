from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from weather_platform import __version__
from weather_platform.config import Settings
from weather_platform.domain.models import Observation
from weather_platform.storage.jsonl import JsonlObservationStore

settings = Settings()
store = JsonlObservationStore(settings.observation_path)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Global Probabilistic Weather Platform",
    version=__version__,
    lifespan=lifespan,
)


def problem_response(
    request: Request,
    *,
    status_code: int,
    problem_type: str,
    title: str,
    detail: str,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    content: dict[str, Any] = {
        "type": problem_type,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": str(request.url.path),
    }
    if extra:
        content.update(extra)
    return JSONResponse(
        status_code=status_code,
        content=content,
        media_type="application/problem+json",
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return problem_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        problem_type="urn:weather:problem:invalid-request",
        title="Invalid request",
        detail="request validation failed",
        extra={"errors": jsonable_encoder(exc.errors())},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return problem_response(
        request,
        status_code=exc.status_code,
        problem_type="about:blank",
        title=HTTPStatus(exc.status_code).phrase,
        detail=str(exc.detail),
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    # Client input failures surface as RequestValidationError before endpoints run,
    # so a ValueError reaching this handler is a service-side fault, not a bad request.
    return problem_response(
        request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        problem_type="urn:weather:problem:internal-error",
        title="Internal error",
        detail=str(exc),
    )


@app.get("/healthz")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": __version__,
        "environment": settings.environment,
        "telemetry_enabled": settings.internal_otel_endpoint is not None,
        "external_egress_enabled": settings.allow_external_egress,
    }


@app.post("/v1/observations", status_code=status.HTTP_202_ACCEPTED)
def create_observation(observation: Observation) -> dict[str, str]:
    if observation.quality_disposition.value == "reject":
        raise HTTPException(
            status_code=422,
            detail="rejected observations cannot enter the canonical store",
        )
    store.append(observation)
    return {"observation_id": str(observation.observation_id), "status": "accepted"}


@app.get("/v1/observations", response_model=list[Observation])
def list_observations(
    phenomenon: str | None = Query(default=None, pattern=r"^[a-z][a-z0-9_]*$"),
    limit: int = Query(default=100, ge=1, le=10_000),
) -> list[Observation]:
    return store.list(phenomenon=phenomenon, limit=limit)


def run() -> None:
    uvicorn.run("weather_platform.api.main:app", host="127.0.0.1", port=8080)

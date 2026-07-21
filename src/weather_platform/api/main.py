from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

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


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "type": "urn:weather:problem:invalid-value",
            "title": "Invalid value",
            "status": 422,
            "detail": str(exc),
            "instance": str(request.url.path),
        },
        media_type="application/problem+json",
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

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from weather_platform import __version__
from weather_platform.config import Settings
from weather_platform.domain.models import Observation
from weather_platform.ingestion.adapters.json_observation import JsonObservationAdapter
from weather_platform.ingestion.service import IngestionService
from weather_platform.storage.jsonl import JsonlObservationStore
from weather_platform.storage.raw_objects import FileSystemRawObjectStore

settings = Settings()
store = JsonlObservationStore(settings.observation_path)
raw_store = FileSystemRawObjectStore(
    settings.raw_object_dir,
    max_object_bytes=settings.max_raw_object_bytes,
)
ingestion_service = IngestionService(raw_store, store)
json_adapter = JsonObservationAdapter()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.raw_object_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Global Probabilistic Weather Platform",
    version=__version__,
    lifespan=lifespan,
)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
        "raw_object_store": "filesystem-sha256",
    }


@app.post("/v1/observations", status_code=status.HTTP_202_ACCEPTED)
async def create_observation(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="content-type must be application/json",
        )
    payload = await request.body()
    if not payload:
        raise ValueError("source record must not be empty")

    result = ingestion_service.ingest(json_adapter, payload)
    return {
        "status": "accepted",
        "raw_object_digest": result.raw_object.digest,
        "raw_object_uri": result.raw_object.uri,
        "raw_object_created": result.raw_object.created,
        "observations_written": result.observations_written,
        "duplicate": result.duplicate,
        "observation_ids": [str(identifier) for identifier in result.observation_ids],
    }


@app.get("/v1/observations", response_model=list[Observation])
def list_observations(
    phenomenon: str | None = Query(default=None, pattern=r"^[a-z][a-z0-9_]*$"),
    limit: int = Query(default=100, ge=1, le=10_000),
) -> list[Observation]:
    return store.list(phenomenon=phenomenon, limit=limit)


def run() -> None:
    uvicorn.run("weather_platform.api.main:app", host="127.0.0.1", port=8080)

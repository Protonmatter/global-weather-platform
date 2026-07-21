import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Path, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from weather_platform import __version__
from weather_platform.config import Settings
from weather_platform.domain.models import Observation
from weather_platform.ingestion.adapters.json_observation import JsonObservationAdapter
from weather_platform.ingestion.pipeline import SourceDecodeError, ingest_source_record
from weather_platform.provenance import sha256_digest
from weather_platform.storage.jsonl import JsonlObservationStore
from weather_platform.storage.raw import RawSourceStore

settings = Settings()
store = JsonlObservationStore(settings.observation_path)
raw_store = RawSourceStore(settings.raw_source_dir)
adapter = JsonObservationAdapter()
_ingest_lock = threading.Lock()


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


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Keeps the problem+json contract for faults such as OSError from storage;
    # the detail stays generic because arbitrary exception text may leak internals.
    return problem_response(
        request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        problem_type="urn:weather:problem:internal-error",
        title="Internal error",
        detail="unexpected internal error",
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


def _admit_observations(observations: list[Observation]) -> None:
    # A byte-identical redelivery decodes to an equal observation and is skipped;
    # a differing record under an existing id is a conflict, never a silent drop.
    # The check-then-append pair must be atomic across threadpool workers; a
    # process lock suffices because the service deploys as a single process.
    with _ingest_lock:
        existing = {
            observation.observation_id: observation for observation in store.iter_observations()
        }
        for observation in observations:
            current = existing.get(observation.observation_id)
            if current is None:
                store.append(observation)
                existing[observation.observation_id] = observation
            elif current != observation:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"observation {observation.observation_id} conflicts with "
                        f"an existing canonical record"
                    ),
                )


def _require_retained_source(digest: str) -> None:
    if not raw_store.exists(digest):
        raise HTTPException(
            status_code=422,
            detail="observation provenance must reference a retained source record",
        )
    # Integrity-verifies the retained bytes; corruption surfaces as an internal
    # fault instead of admitting an observation whose source cannot be retrieved.
    raw_store.retrieve(digest)


@app.post("/v1/observations", status_code=status.HTTP_202_ACCEPTED)
def create_observation(observation: Observation) -> dict[str, str]:
    if observation.quality_disposition.value == "reject":
        raise HTTPException(
            status_code=422,
            detail="rejected observations cannot enter the canonical store",
        )
    _require_retained_source(observation.provenance.source_record_digest)
    _admit_observations([observation])
    return {"observation_id": str(observation.observation_id), "status": "accepted"}


def _ingest_and_store(payload: bytes) -> dict[str, Any]:
    try:
        result = ingest_source_record(payload, adapter=adapter, raw_store=raw_store)
    except SourceDecodeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if any(
        observation.quality_disposition.value == "reject" for observation in result.observations
    ):
        raise HTTPException(
            status_code=422,
            detail="rejected observations cannot enter the canonical store",
        )
    _admit_observations(result.observations)
    return {
        "source_record_digest": result.source_record_digest,
        "observation_ids": [str(observation.observation_id) for observation in result.observations],
        "status": "accepted",
    }


@app.post("/v1/source-records", status_code=status.HTTP_202_ACCEPTED)
async def create_source_record(request: Request) -> dict[str, Any]:
    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=422, detail="source record payload must not be empty")
    # Retention writes and fsyncs; run it off the event loop.
    return await run_in_threadpool(_ingest_and_store, payload)


@app.put("/v1/source-records/{digest}")
async def put_source_record(
    request: Request, digest: str = Path(pattern=r"^sha256:[a-f0-9]{64}$")
) -> JSONResponse:
    """Retain source bytes without decoding, for externally decoded observations."""
    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=422, detail="source record payload must not be empty")
    if sha256_digest(payload) != digest:
        raise HTTPException(
            status_code=422,
            detail="payload does not match the requested source record digest",
        )
    already_retained = raw_store.exists(digest)
    await run_in_threadpool(raw_store.store, payload)
    return JSONResponse(
        status_code=status.HTTP_200_OK if already_retained else status.HTTP_201_CREATED,
        content={"source_record_digest": digest, "status": "retained"},
    )


@app.get("/v1/source-records/{digest}")
def get_source_record(digest: str = Path(pattern=r"^sha256:[a-f0-9]{64}$")) -> Response:
    if not raw_store.exists(digest):
        raise HTTPException(status_code=404, detail="source record not found")
    return Response(content=raw_store.retrieve(digest), media_type="application/octet-stream")


@app.get("/v1/observations", response_model=list[Observation])
def list_observations(
    phenomenon: str | None = Query(default=None, pattern=r"^[a-z][a-z0-9_]*$"),
    limit: int = Query(default=100, ge=1, le=10_000),
) -> list[Observation]:
    return store.list(phenomenon=phenomenon, limit=limit)


def run() -> None:
    uvicorn.run("weather_platform.api.main:app", host="127.0.0.1", port=8080)

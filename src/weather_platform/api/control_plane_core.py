import uuid
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from http import HTTPStatus
from secrets import compare_digest
from typing import Annotated, Any

import uvicorn
from fastapi import FastAPI, HTTPException, Path, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from weather_platform import __version__
from weather_platform.api import edr
from weather_platform.config import Settings
from weather_platform.domain.model_catalog import GuidanceOrigin, ModelGuidanceCycle
from weather_platform.domain.models import DigestVerification, Observation, QualityDisposition
from weather_platform.ingestion.adapters.json_observation import JsonObservationAdapter
from weather_platform.ingestion.eccodes_backend import (
    EccodesUnavailableError,
    grib_field_inventory,
    runtime_decoder_version,
)
from weather_platform.ingestion.pipeline import SourceDecodeError, ingest_source_record
from weather_platform.provenance import sha256_digest
from weather_platform.storage.jsonl import JsonlObservationStore
from weather_platform.storage.model_catalog_store import ModelGuidanceCatalog
from weather_platform.storage.raw import RawSourceStore

settings = Settings()
store = JsonlObservationStore(settings.observation_path)
raw_store = RawSourceStore(
    settings.raw_source_dir,
    max_record_bytes=settings.max_source_record_bytes,
)
model_catalog = ModelGuidanceCatalog(settings.model_catalog_path)
adapter = JsonObservationAdapter()
MODEL_CYCLE_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "urn:weather:model-cycle-id")


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
    headers: Mapping[str, str] | None = None,
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
        headers=headers,
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
    # Protocol headers such as Allow on 405 must survive the problem+json rewrite.
    return problem_response(
        request,
        status_code=exc.status_code,
        problem_type="about:blank",
        title=HTTPStatus(exc.status_code).phrase,
        detail=str(exc.detail),
        headers=exc.headers,
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
        "max_source_record_bytes": raw_store.max_record_bytes,
        "mutation_authentication_enabled": settings.control_plane_token is not None,
    }


def _require_mutation_authorization(request: Request) -> str:
    """Authorize an authenticated BFF mutation without logging its secret."""
    configured = settings.control_plane_token
    if configured is None:
        # Local development retains the existing direct API workflow. Settings
        # prevents production startup without an explicitly injected token.
        return "development"
    authorization = request.headers.get("authorization", "")
    scheme, separator, supplied = authorization.partition(" ")
    expected = configured.get_secret_value()
    if separator != " " or scheme.casefold() != "bearer" or not compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="valid control-plane service authentication is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    actor = request.headers.get("x-weather-actor", "").strip()
    if not actor:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="an authenticated operator identity is required",
        )
    return actor


def _observation_content(observation: Observation) -> dict[str, Any]:
    # Receipt time and transport URL are acquisition metadata, not observed
    # content: origin/cache redeliveries of identical source bytes can arrive at
    # different times and URLs. The stable retained digest still participates
    # in the comparison, and the first record keeps its acquisition metadata.
    return observation.model_dump(
        mode="json",
        exclude={
            "ingestion_time": True,
            "provenance": {
                "digest_verification",
                "received_at",
                "ingested_at",
                "source_uri",
            },
        },
    )


def _with_platform_verification(observation: Observation) -> Observation:
    """Keep upstream trust claims reserved for the WIS2 verification path."""
    provenance = observation.provenance.model_copy(
        update={"digest_verification": DigestVerification.PLATFORM}
    )
    return observation.model_copy(update={"provenance": provenance})


def _admit_observations(
    observations: list[Observation],
    *,
    mutation_id: uuid.UUID | None = None,
    source_record_digest: str | None = None,
) -> None:
    # A redelivery with identical content is skipped; a differing record under
    # an existing id is a conflict, never a silent drop. The whole batch is
    # conflict-checked before any append so a rejected source record never
    # leaves a partial batch behind. The store transaction makes the
    # check-then-append atomic across both threadpool workers and processes.
    with store.transaction():
        existing = {
            observation.observation_id: observation for observation in store.iter_observations()
        }
        to_append: list[Observation] = []
        canonical_observations: list[Observation] = []
        for observation in observations:
            current = existing.get(observation.observation_id)
            if current is None:
                existing[observation.observation_id] = observation
                to_append.append(observation)
                canonical_observations.append(observation)
            elif _observation_content(current) != _observation_content(observation):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"observation {observation.observation_id} conflicts with "
                        f"an existing canonical record"
                    ),
                )
            else:
                canonical_observations.append(current)
        if mutation_id is not None:
            if source_record_digest is None:
                raise ValueError("an ingestion mutation requires its source record digest")
            # The receipt is the final line of the same durable append payload
            # as the canonical batch. A crash can expose observations without
            # a receipt, but can never expose a receipt before its observations.
            store.commit_ingestion_batch(
                mutation_id,
                source_digest=source_record_digest,
                appended_observations=to_append,
                canonical_observations=canonical_observations,
            )
        else:
            for observation in to_append:
                store.append(observation)


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
def create_observation(request: Request, observation: Observation) -> dict[str, str]:
    _require_mutation_authorization(request)
    if observation.quality_disposition.value == "reject":
        raise HTTPException(
            status_code=422,
            detail="rejected observations cannot enter the canonical store",
        )
    _require_retained_source(observation.provenance.source_record_digest)
    observation = _with_platform_verification(observation)
    _admit_observations([observation])
    return {"observation_id": str(observation.observation_id), "status": "accepted"}


def _ingest_and_store(
    payload: bytes,
    *,
    mutation_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    try:
        result = ingest_source_record(payload, adapter=adapter, raw_store=raw_store)
    except SourceDecodeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    observations = [_with_platform_verification(item) for item in result.observations]
    if any(
        observation.quality_disposition.value == "reject" for observation in result.observations
    ):
        raise HTTPException(
            status_code=422,
            detail="rejected observations cannot enter the canonical store",
        )
    _admit_observations(
        observations,
        mutation_id=mutation_id,
        source_record_digest=result.source_record_digest,
    )
    return {
        "source_record_digest": result.source_record_digest,
        "observation_ids": [str(observation.observation_id) for observation in observations],
        "status": "accepted",
    }


async def _read_bounded_source_record(request: Request) -> bytes:
    """Read a request body without buffering beyond the configured retention limit."""
    maximum = raw_store.max_record_bytes
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid Content-Length header") from exc
        if declared_length < 0:
            raise HTTPException(status_code=400, detail="invalid Content-Length header")
        if declared_length > maximum:
            raise HTTPException(
                status_code=413,
                detail=f"source record exceeds the {maximum}-byte retention limit",
            )

    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > maximum:
            raise HTTPException(
                status_code=413,
                detail=f"source record exceeds the {maximum}-byte retention limit",
            )
        payload.extend(chunk)
    return bytes(payload)


@app.post("/v1/source-records", status_code=status.HTTP_202_ACCEPTED)
async def create_source_record(request: Request) -> dict[str, Any]:
    _require_mutation_authorization(request)
    payload = await _read_bounded_source_record(request)
    if not payload:
        raise HTTPException(status_code=422, detail="source record payload must not be empty")
    # Retention writes and fsyncs; run it off the event loop.
    return await run_in_threadpool(_ingest_and_store, payload)


def _verify_and_retain(payload: bytes, digest: str) -> bool:
    """Retain the payload under its digest; return whether it was already retained."""
    if sha256_digest(payload) != digest:
        raise HTTPException(
            status_code=422,
            detail="payload does not match the requested source record digest",
        )
    already_retained = raw_store.exists(digest)
    raw_store.store(payload)
    return already_retained


@app.put("/v1/source-records/{digest}")
async def put_source_record(
    request: Request, digest: str = Path(pattern=r"^sha256:[a-f0-9]{64}$")
) -> JSONResponse:
    """Retain source bytes without decoding, for externally decoded observations."""
    _require_mutation_authorization(request)
    payload = await _read_bounded_source_record(request)
    if not payload:
        raise HTTPException(status_code=422, detail="source record payload must not be empty")
    # Hashing large payloads is CPU work; keep it off the event loop with the store.
    already_retained = await run_in_threadpool(_verify_and_retain, payload, digest)
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
    include_quarantined: bool = Query(
        default=False,
        description="Include observations held in quarantine pending quality review.",
    ),
) -> list[Observation]:
    return store.list(phenomenon=phenomenon, limit=limit, include_quarantined=include_quarantined)


def _cycle_summary(cycle: ModelGuidanceCycle) -> dict[str, Any]:
    cycle_name = "|".join(cycle.cycle_key())
    return {
        "id": str(uuid.uuid5(MODEL_CYCLE_ID_NAMESPACE, cycle_name)),
        "model_id": cycle.model_id,
        "model_version": cycle.model_version,
        "guidance_origin": cycle.guidance_origin.value,
        "initialized_at": cycle.initialized_at.isoformat(),
        "source_revision": cycle.source_revision,
        "completeness": cycle.completeness().value,
        "missing_field_count": len(cycle.missing_fields()),
        "available_field_count": len(cycle.available_fields),
        "expected_field_count": len(cycle.expected_fields),
        "updated_at": cycle.initialized_at.isoformat(),
    }


@app.post("/v1/model-cycles", status_code=status.HTTP_202_ACCEPTED)
def register_model_cycle(request: Request, cycle: ModelGuidanceCycle) -> dict[str, Any]:
    _require_mutation_authorization(request)
    # guidance_origin is required with no default, so no cycle enters the
    # catalog without an explicit imported/platform/warning/experimental label.
    model_catalog.register(cycle)
    return {**_cycle_summary(cycle), "status": "catalogued"}


@app.get("/v1/model-cycles")
def list_model_cycles(
    model_id: Annotated[str | None, Query(min_length=1)] = None,
    guidance_origin: Annotated[GuidanceOrigin | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=10_000)] = 100,
) -> list[dict[str, Any]]:
    cycles = model_catalog.list(model_id=model_id, guidance_origin=guidance_origin, limit=limit)
    return [_cycle_summary(cycle) for cycle in cycles]


_EDR_COLLECTION = {
    "id": "observations",
    "title": "Canonical observations",
    "description": "Point observations queryable by position and datetime.",
    "crs": ["CRS84"],
    "output_formats": ["GeoJSON"],
    "data_queries": {
        "position": {
            "link": {
                "href": "/v1/edr/collections/observations/position",
                "rel": "data",
                "variables": {"query_type": "position", "output_formats": ["GeoJSON"]},
            }
        }
    },
}


@app.get("/v1/edr/collections")
def edr_collections() -> dict[str, Any]:
    return {"collections": [_EDR_COLLECTION]}


@app.get("/v1/edr/collections/observations/position")
def edr_position(
    coords: str,
    datetime: str | None = None,
    within_degrees: Annotated[float, Query(gt=0, le=45)] = 0.5,
    limit: Annotated[int, Query(ge=1, le=10_000)] = 1000,
    include_quarantined: bool = False,
    parameter_name: Annotated[str | None, Query(alias="parameter-name")] = None,
) -> dict[str, Any]:
    try:
        longitude, latitude = edr.parse_position_coords(coords)
        start, end = edr.parse_datetime_interval(datetime)
    except ValueError as exc:
        # Malformed query is a client error, not the service-side 500 path.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    phenomena = (
        {name.strip() for name in parameter_name.split(",") if name.strip()}
        if parameter_name is not None
        else None
    )
    candidates = (
        observation
        for observation in store.iter_observations()
        if include_quarantined or observation.quality_disposition != QualityDisposition.QUARANTINE
    )
    collection = edr.position_feature_collection(
        candidates,
        longitude=longitude,
        latitude=latitude,
        within_degrees=within_degrees,
        start=start,
        end=end,
        phenomena=phenomena,
        limit=limit,
    )
    return collection


@app.post("/v1/decode/grib-inventory")
async def decode_grib_inventory(request: Request) -> dict[str, Any]:
    """Decode uploaded GRIB2 bytes into the field inventory that drives cycle completeness."""
    _require_mutation_authorization(request)
    payload = await _read_bounded_source_record(request)
    if not payload:
        raise HTTPException(status_code=422, detail="GRIB2 payload must not be empty")
    try:
        fields = await run_in_threadpool(grib_field_inventory, payload)
        version = runtime_decoder_version()
    except EccodesUnavailableError as exc:
        # The decoder extra is not installed in this deployment.
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "decoder_version": version,
        "fields": [field.model_dump(mode="json") for field in fields],
    }


def run() -> None:
    uvicorn.run("weather_platform.api.main:app", host="127.0.0.1", port=8080)

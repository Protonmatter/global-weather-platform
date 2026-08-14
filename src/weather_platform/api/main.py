import sys
import uuid
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path as FilePath
from types import ModuleType
from typing import Any, cast

from fastapi import HTTPException, Path, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute

from weather_platform import __version__
from weather_platform.api import control_plane_core as _core
from weather_platform.api.request_identity import (
    request_id_from_request as _request_id_from_request,
)
from weather_platform.config import Settings
from weather_platform.domain.audit import MutationAuditEvent, MutationResult
from weather_platform.domain.model_catalog import ModelGuidanceCycle
from weather_platform.domain.models import Observation
from weather_platform.provenance import sha256_digest
from weather_platform.storage.audit import AuthoritativeAuditStore
from weather_platform.storage.jsonl import JsonlObservationStore
from weather_platform.storage.model_catalog_store import ModelGuidanceCatalog
from weather_platform.storage.raw import RawSourceStore

app = _core.app
settings = _core.settings
store = _core.store
raw_store = _core.raw_store
model_catalog = _core.model_catalog
adapter = _core.adapter
audit_store = AuthoritativeAuditStore(settings.audit_path)


def _runtime_audit_path(name: str, value: object) -> FilePath | None:
    if name == "settings" and isinstance(value, Settings):
        return value.audit_path
    if name == "store" and isinstance(value, JsonlObservationStore):
        return value.path.parent / settings.audit_filename
    if name == "raw_store" and isinstance(value, RawSourceStore):
        return value.root.parent / settings.audit_filename
    if name == "model_catalog" and isinstance(value, ModelGuidanceCatalog):
        return value.path.parent / settings.audit_filename
    return None


_FORWARDED_RUNTIME_NAMES = frozenset(
    {
        "adapter",
        "model_catalog",
        "raw_store",
        "settings",
        "store",
    }
)


class _ForwardingModule(ModuleType):
    """Keep established test/runtime patch points synchronized with the core."""

    def __setattr__(self, name: str, value: object) -> None:
        if name in _FORWARDED_RUNTIME_NAMES:
            setattr(_core, name, value)
        super().__setattr__(name, value)
        audit_path = _runtime_audit_path(name, value)
        if audit_path is not None:
            super().__setattr__("audit_store", AuthoritativeAuditStore(audit_path))


def __getattr__(name: str) -> Any:
    return getattr(_core, name)


cast(Any, sys.modules[__name__]).__class__ = _ForwardingModule


@app.middleware("http")
async def request_identity_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = _request_id_from_request(request)
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["x-request-id"] = str(request_id)
    return response


def _mutation_event(
    request: Request,
    *,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    result: MutationResult,
    detail: dict[str, Any] | None = None,
) -> MutationAuditEvent:
    return MutationAuditEvent(
        event_id=uuid.uuid4(),
        request_id=_request_id_from_request(request),
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        occurred_at=datetime.now(UTC),
        software_version=__version__,
        detail=detail or {},
    )


def _record_mutation_event(
    request: Request,
    *,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    result: MutationResult,
    detail: dict[str, Any] | None = None,
) -> None:
    audit_store.append(
        _mutation_event(
            request,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            detail=detail,
        )
    )


def _prepare_success_event(
    request: Request,
    *,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict[str, Any],
) -> uuid.UUID:
    return audit_store.prepare_terminal(
        _mutation_event(
            request,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=MutationResult.SUCCEEDED,
            detail=detail,
        )
    )


def _record_failed_mutation(
    request: Request,
    *,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    error: Exception,
) -> None:
    _record_mutation_event(
        request,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=MutationResult.FAILED,
        detail={"error_type": type(error).__name__},
    )


@contextmanager
def _audited_mutation(
    request: Request,
    *,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict[str, Any],
) -> Iterator[None]:
    _record_mutation_event(
        request,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=MutationResult.ATTEMPTED,
        detail=detail,
    )
    terminal_event_id = _prepare_success_event(
        request,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
    )
    try:
        yield
    except Exception as error:
        audit_store.discard_terminal(terminal_event_id)
        _record_failed_mutation(
            request,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            error=error,
        )
        raise
    audit_store.commit_terminal(terminal_event_id)


def _remove_route(path: str, method: str) -> None:
    app.router.routes[:] = [
        route
        for route in app.router.routes
        if not (
            isinstance(route, APIRoute)
            and route.path == path
            and method in (route.methods or set())
        )
    ]


for _path, _method in (
    ("/v1/observations", "POST"),
    ("/v1/source-records", "POST"),
    ("/v1/source-records/{digest}", "PUT"),
    ("/v1/source-records/{digest}", "GET"),
    ("/v1/model-cycles", "POST"),
):
    _remove_route(_path, _method)


@app.post("/v1/observations", status_code=status.HTTP_202_ACCEPTED)
def create_observation(request: Request, observation: Observation) -> dict[str, str]:
    actor = _core._require_mutation_authorization(request)
    resource_id = str(observation.observation_id)
    detail = {
        "phenomenon": observation.phenomenon,
        "quality_disposition": observation.quality_disposition.value,
    }
    with _audited_mutation(
        request,
        actor=actor,
        action="observation.admitted",
        resource_type="observation",
        resource_id=resource_id,
        detail=detail,
    ):
        if observation.quality_disposition.value == "reject":
            raise HTTPException(
                status_code=422,
                detail="rejected observations cannot enter the canonical store",
            )
        _core._require_retained_source(observation.provenance.source_record_digest)
        admitted = _core._with_platform_verification(observation)
        _core._admit_observations([admitted])
    return {"observation_id": resource_id, "status": "accepted"}


@app.post("/v1/source-records", status_code=status.HTTP_202_ACCEPTED)
async def create_source_record(request: Request) -> dict[str, Any]:
    actor = _core._require_mutation_authorization(request)
    payload = await _core._read_bounded_source_record(request)
    if not payload:
        raise HTTPException(status_code=422, detail="source record payload must not be empty")
    digest = sha256_digest(payload)
    detail = {"byte_length": len(payload)}
    with _audited_mutation(
        request,
        actor=actor,
        action="source_record.ingested",
        resource_type="source_record",
        resource_id=digest,
        detail=detail,
    ):
        response = await run_in_threadpool(_core._ingest_and_store, payload)
    return response


@app.put("/v1/source-records/{digest}")
async def put_source_record(
    request: Request,
    digest: str = Path(pattern=r"^sha256:[a-f0-9]{64}$"),
) -> JSONResponse:
    """Retain source bytes without decoding, for externally decoded observations."""

    actor = _core._require_mutation_authorization(request)
    payload = await _core._read_bounded_source_record(request)
    if not payload:
        raise HTTPException(status_code=422, detail="source record payload must not be empty")
    detail = {"byte_length": len(payload)}
    with _audited_mutation(
        request,
        actor=actor,
        action="source_record.retained",
        resource_type="source_record",
        resource_id=digest,
        detail=detail,
    ):
        already_retained = await run_in_threadpool(_core._verify_and_retain, payload, digest)
    return JSONResponse(
        status_code=status.HTTP_200_OK if already_retained else status.HTTP_201_CREATED,
        content={"source_record_digest": digest, "status": "retained"},
    )


@app.get("/v1/source-records/{digest}")
def get_source_record(
    request: Request,
    digest: str = Path(pattern=r"^sha256:[a-f0-9]{64}$"),
) -> Response:
    _core._require_mutation_authorization(request)
    if not _core.raw_store.exists(digest):
        raise HTTPException(status_code=404, detail="source record not found")
    return Response(
        content=_core.raw_store.retrieve(digest),
        media_type="application/octet-stream",
    )


@app.post("/v1/model-cycles", status_code=status.HTTP_202_ACCEPTED)
def register_model_cycle(request: Request, cycle: ModelGuidanceCycle) -> dict[str, Any]:
    actor = _core._require_mutation_authorization(request)
    summary = _core._cycle_summary(cycle)
    resource_id = str(summary["id"])
    detail = {
        "completeness": str(summary["completeness"]),
        "guidance_origin": cycle.guidance_origin.value,
    }
    with _audited_mutation(
        request,
        actor=actor,
        action="model_cycle.catalogued",
        resource_type="model_cycle",
        resource_id=resource_id,
        detail=detail,
    ):
        _core.model_catalog.register(cycle)
    return {**summary, "status": "catalogued"}


app.openapi_schema = None
run = _core.run

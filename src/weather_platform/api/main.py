import sys
import uuid
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path as FilePath
from types import ModuleType
from typing import Any, cast

from fastapi import HTTPException, Path, Query, Request, status
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
from weather_platform.ingestion.pipeline import SourceDecodeError
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
    event_id: uuid.UUID | None = None,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    result: MutationResult,
    detail: dict[str, Any] | None = None,
) -> MutationAuditEvent:
    return MutationAuditEvent(
        event_id=event_id or uuid.uuid4(),
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
    success = _mutation_event(
        request,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=MutationResult.SUCCEEDED,
        detail=detail,
    )
    try:
        return audit_store.prepare_terminal(success)
    except Exception as error:
        audit_store.commit_failure(
            success.event_id,
            _failed_mutation_event(
                request,
                event_id=success.event_id,
                actor=actor,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                error=error,
            ),
        )
        raise


def _failed_mutation_event(
    request: Request,
    *,
    event_id: uuid.UUID,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    error: Exception,
) -> MutationAuditEvent:
    underlying: BaseException = error
    decode_error: SourceDecodeError | None = None
    if isinstance(underlying, SourceDecodeError):
        decode_error = underlying
    while underlying.__cause__ is not None:
        underlying = underlying.__cause__
        if isinstance(underlying, SourceDecodeError):
            decode_error = underlying
    reported_error = decode_error or underlying
    failure_detail: dict[str, Any] = {"error_type": type(reported_error).__name__}
    if action == "source_record.ingested":
        try:
            retained = raw_store.exists(resource_id)
            if retained:
                raw_store.retrieve(resource_id)
        except (OSError, ValueError):
            retained = False
        if retained:
            failure_detail["retained"] = True
    return _mutation_event(
        request,
        event_id=event_id,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=MutationResult.FAILED,
        detail=failure_detail,
    )


def _canonical_mutation_succeeded(event: MutationAuditEvent) -> bool:
    """Return true only when canonical storage proves a prepared success."""

    if event.action == "source_record.retained":
        # Retained bytes are content-addressed and may predate this request.
        # Only the audit store's request-specific applied receipt can prove
        # completion for this action.
        return False
    if event.action == "observation.admitted":
        # An identical canonical observation may also predate this request.
        # Generic state therefore cannot prove that this mutation completed.
        return False
    if event.action == "model_cycle.catalogued":
        expected_digest = event.detail.get("content_digest")
        if not isinstance(expected_digest, str):
            return False
        return model_catalog.contains_mutation(event.event_id, expected_digest)
    if event.action == "source_record.ingested":
        if not raw_store.exists(event.resource_id):
            return False
        raw_store.retrieve(event.resource_id)
        return store.contains_ingestion_mutation(event.event_id, event.resource_id)
    return False


def _reconcile_pending_audit() -> None:
    audit_store.reconcile_pending(_canonical_mutation_succeeded)


@contextmanager
def _audited_mutation(
    request: Request,
    *,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict[str, Any],
) -> Iterator[uuid.UUID]:
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
        yield terminal_event_id
    except Exception as error:
        audit_store.commit_failure(
            terminal_event_id,
            _failed_mutation_event(
                request,
                event_id=terminal_event_id,
                actor=actor,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                error=error,
            ),
        )
        raise
    audit_store.mark_applied(terminal_event_id)
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


@app.get("/v1/audit-events")
def list_audit_events(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1_000),
) -> dict[str, list[dict[str, Any]]]:
    """Return recent authoritative mutation events to an authenticated BFF."""

    _core._require_mutation_authorization(request)
    events = audit_store.iter_recent_events(limit)
    return {"events": [event.model_dump(mode="json") for event in events]}


@app.post("/v1/observations", status_code=status.HTTP_202_ACCEPTED)
def create_observation(request: Request, observation: Observation) -> dict[str, str]:
    actor = _core._require_mutation_authorization(request)
    resource_id = str(observation.observation_id)
    admitted = _core._with_platform_verification(observation)
    detail = {
        "phenomenon": observation.phenomenon,
        "quality_disposition": observation.quality_disposition.value,
        "content_digest": sha256_digest(admitted.model_dump_json().encode("utf-8")),
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
    ) as mutation_id:
        response = await run_in_threadpool(
            _core._ingest_and_store,
            payload,
            mutation_id=mutation_id,
        )
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
        "content_digest": sha256_digest(cycle.model_dump_json().encode("utf-8")),
        "guidance_origin": cycle.guidance_origin.value,
    }
    with _audited_mutation(
        request,
        actor=actor,
        action="model_cycle.catalogued",
        resource_type="model_cycle",
        resource_id=resource_id,
        detail=detail,
    ) as mutation_id:
        _core.model_catalog.register(cycle, mutation_id=mutation_id)
    return {**summary, "status": "catalogued"}


app.openapi_schema = None
_reconcile_pending_audit()
run = _core.run

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from weather_platform.api import main
from weather_platform.config import Settings
from weather_platform.domain.audit import MutationAuditEvent, MutationResult
from weather_platform.domain.model_catalog import (
    GuidanceOrigin,
    ModelCycleField,
    ModelGuidanceCycle,
)
from weather_platform.domain.models import Observation
from weather_platform.provenance import sha256_digest
from weather_platform.storage.audit import AuthoritativeAuditStore
from weather_platform.storage.jsonl import JsonlObservationStore
from weather_platform.storage.model_catalog_store import ModelGuidanceCatalog
from weather_platform.storage.raw import RawSourceStore


def isolated_client(
    tmp_path: Path,
    monkeypatch,
    *,
    production: bool = False,
    raise_server_exceptions: bool = True,
):
    credential = "x" * 32 if production else None
    settings = Settings(
        _env_file=None,
        environment="production" if production else "test",
        data_dir=tmp_path,
        control_plane_token=credential,
    )
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "store", JsonlObservationStore(settings.observation_path))
    monkeypatch.setattr(main, "raw_store", RawSourceStore(settings.raw_source_dir))
    monkeypatch.setattr(
        main,
        "model_catalog",
        ModelGuidanceCatalog(settings.model_catalog_path),
    )
    monkeypatch.setattr(main, "audit_store", AuthoritativeAuditStore(settings.audit_path))
    return (
        TestClient(main.app, raise_server_exceptions=raise_server_exceptions),
        credential,
    )


def service_headers(credential: str, request_id: str | None = None) -> dict[str, str]:
    headers = {
        "authorization": f"Bearer {credential}",
        "x-weather-actor": "operator@example.invalid",
    }
    if request_id is not None:
        headers["x-request-id"] = request_id
    return headers


def succeeded_event(
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict | None = None,
) -> MutationAuditEvent:
    return MutationAuditEvent(
        event_id=uuid4(),
        request_id=uuid4(),
        actor="operator@example.invalid",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=MutationResult.SUCCEEDED,
        occurred_at=datetime.now(UTC),
        software_version=main.__version__,
        detail=detail or {},
    )


def test_request_identifier_is_echoed_and_bound_to_audit_events(tmp_path, monkeypatch) -> None:
    client, _ = isolated_client(tmp_path, monkeypatch)
    request_id = str(uuid4())
    payload = b"audited source record"
    digest = sha256_digest(payload)

    response = client.put(
        f"/v1/source-records/{digest}",
        content=payload,
        headers={"x-request-id": request_id},
    )

    assert response.status_code == 201
    assert response.headers["x-request-id"] == request_id
    events = list(main.audit_store.iter_events())
    assert [event.result.value for event in events] == ["attempted", "succeeded"]
    assert {str(event.request_id) for event in events} == {request_id}
    assert {event.resource_id for event in events} == {digest}


def test_failed_mutation_has_a_terminal_failed_event(tmp_path, monkeypatch) -> None:
    client, _ = isolated_client(tmp_path, monkeypatch)
    payload = b"wrong digest payload"
    requested_digest = "sha256:" + "a" * 64

    response = client.put(f"/v1/source-records/{requested_digest}", content=payload)

    assert response.status_code == 422
    events = list(main.audit_store.iter_events())
    assert [event.result.value for event in events] == ["attempted", "failed"]
    assert events[0].request_id == events[1].request_id


def test_initial_audit_failure_prevents_source_retention(tmp_path, monkeypatch) -> None:
    client, _ = isolated_client(
        tmp_path,
        monkeypatch,
        raise_server_exceptions=False,
    )
    payload = b"must not be retained"
    digest = sha256_digest(payload)

    def fail_append(_event) -> None:
        raise OSError("audit storage unavailable")

    monkeypatch.setattr(main.audit_store, "append", fail_append)
    response = client.put(f"/v1/source-records/{digest}", content=payload)

    assert response.status_code == 500
    assert not main.raw_store.exists(digest)


def test_terminal_audit_append_failure_preserves_authoritative_success(
    tmp_path,
    monkeypatch,
) -> None:
    client, _ = isolated_client(tmp_path, monkeypatch)
    payload = b"terminal audit outbox"
    digest = sha256_digest(payload)
    append = main.audit_store.append

    def fail_terminal_append(event) -> None:
        if event.result == MutationResult.SUCCEEDED:
            raise OSError("audit ledger is full")
        append(event)

    monkeypatch.setattr(main.audit_store, "append", fail_terminal_append)
    response = client.put(f"/v1/source-records/{digest}", content=payload)

    assert response.status_code == 201
    assert main.raw_store.retrieve(digest) == payload
    assert [event.result for event in main.audit_store.iter_events()] == [
        MutationResult.ATTEMPTED,
        MutationResult.SUCCEEDED,
    ]


def test_restart_reconciles_success_committed_before_terminal_audit(tmp_path, monkeypatch) -> None:
    client, _ = isolated_client(tmp_path, monkeypatch)
    payload = b"restart recovery evidence"
    digest = sha256_digest(payload)
    monkeypatch.setattr(main.audit_store, "commit_terminal", lambda _event_id: None)

    response = client.put(f"/v1/source-records/{digest}", content=payload)

    assert response.status_code == 201
    assert [event.result for event in main.audit_store.iter_events()] == [MutationResult.ATTEMPTED]
    main.audit_store = AuthoritativeAuditStore(main.settings.audit_path)
    main._reconcile_pending_audit()
    assert [event.result for event in main.audit_store.iter_events()] == [
        MutationResult.ATTEMPTED,
        MutationResult.SUCCEEDED,
    ]


def test_restart_reconciles_completed_source_ingestion(tmp_path, monkeypatch) -> None:
    client, _ = isolated_client(tmp_path, monkeypatch)
    payload = (
        Path(__file__).resolve().parents[2] / "testdata/observations/temperature.json"
    ).read_bytes()
    monkeypatch.setattr(main.audit_store, "commit_terminal", lambda _event_id: None)

    response = client.post("/v1/source-records", content=payload)

    assert response.status_code == 202
    main.audit_store = AuthoritativeAuditStore(main.settings.audit_path)
    main._reconcile_pending_audit()
    assert [event.result for event in main.audit_store.iter_events()] == [
        MutationResult.ATTEMPTED,
        MutationResult.SUCCEEDED,
    ]
    assert not list(main.audit_store.pending_events())


def test_restart_reconciles_model_cycle_appended_by_the_same_mutation(
    tmp_path,
    monkeypatch,
) -> None:
    client, _ = isolated_client(tmp_path, monkeypatch)
    field = ModelCycleField(
        variable="air_temperature",
        level_type="surface",
        grid="global-0.25-degree",
        lead_hours=0,
    )
    cycle = ModelGuidanceCycle(
        model_id="gfs",
        model_version="v16",
        guidance_origin=GuidanceOrigin.IMPORTED,
        initialized_at=datetime(2026, 8, 13, tzinfo=UTC),
        source_revision="revision-1",
        grids=[field.grid],
        expected_fields=[field],
        available_fields=[field],
    )
    monkeypatch.setattr(main.audit_store, "commit_terminal", lambda _event_id: None)

    response = client.post("/v1/model-cycles", json=cycle.model_dump(mode="json"))

    assert response.status_code == 202
    main.audit_store = AuthoritativeAuditStore(main.settings.audit_path)
    main._reconcile_pending_audit()
    assert [event.result for event in main.audit_store.iter_events()] == [
        MutationResult.ATTEMPTED,
        MutationResult.SUCCEEDED,
    ]
    assert not list(main.audit_store.pending_events())


def test_restart_keeps_undecodable_ingestion_success_pending(tmp_path, monkeypatch) -> None:
    client, _ = isolated_client(tmp_path, monkeypatch)
    payload = b"retained but undecodable after interruption"
    monkeypatch.setattr(main.audit_store, "discard_terminal", lambda _event_id: None)

    response = client.post("/v1/source-records", content=payload)

    assert response.status_code == 422
    main.audit_store = AuthoritativeAuditStore(main.settings.audit_path)
    main._reconcile_pending_audit()
    assert [event.result for event in main.audit_store.iter_events()] == [
        MutationResult.ATTEMPTED,
        MutationResult.FAILED,
    ]
    pending = list(main.audit_store.pending_events())
    assert len(pending) == 1
    assert pending[0].action == "source_record.ingested"


@pytest.mark.parametrize(
    ("action", "resource_type", "resource_id", "detail"),
    [
        ("source_record.retained", "source_record", "sha256:" + "a" * 64, {}),
        ("observation.admitted", "observation", str(UUID(int=1)), {}),
        ("model_cycle.catalogued", "model_cycle", str(UUID(int=2)), {}),
        ("source_record.ingested", "source_record", "sha256:" + "b" * 64, {}),
        ("future.unknown", "future_resource", "resource-1", {}),
    ],
)
def test_restart_leaves_unproven_success_pending(
    tmp_path,
    monkeypatch,
    action,
    resource_type,
    resource_id,
    detail,
) -> None:
    isolated_client(tmp_path, monkeypatch)
    event = succeeded_event(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
    )

    assert main._canonical_mutation_succeeded(event) is False


def test_restart_does_not_publish_rejected_source_ingestion(tmp_path, monkeypatch) -> None:
    isolated_client(tmp_path, monkeypatch)
    record = json.loads(
        (Path(__file__).resolve().parents[2] / "testdata/observations/temperature.json").read_text()
    )
    record["quality_disposition"] = "reject"
    payload = json.dumps(record).encode()
    digest = main.raw_store.store(payload)
    event = succeeded_event(
        action="source_record.ingested",
        resource_type="source_record",
        resource_id=digest,
        detail={"byte_length": len(payload)},
    )

    assert main._canonical_mutation_succeeded(event) is False


def test_empty_raw_deposit_is_rejected_before_audit(tmp_path, monkeypatch) -> None:
    client, _ = isolated_client(tmp_path, monkeypatch)

    response = client.put(f"/v1/source-records/sha256:{'a' * 64}", content=b"")

    assert response.status_code == 422
    assert list(main.audit_store.iter_events()) == []


def test_restart_does_not_publish_conflicting_observation_as_success(
    tmp_path,
    monkeypatch,
) -> None:
    isolated_client(tmp_path, monkeypatch)
    record = json.loads(
        (Path(__file__).resolve().parents[2] / "testdata/observations/temperature.json").read_text()
    )
    expected = Observation.model_validate(record)
    conflicting = expected.model_copy(update={"value": 280.0})
    main.store.append(conflicting)
    request_id = uuid4()
    attempted = MutationAuditEvent(
        event_id=uuid4(),
        request_id=request_id,
        actor="operator@example.invalid",
        action="observation.admitted",
        resource_type="observation",
        resource_id=str(expected.observation_id),
        result=MutationResult.ATTEMPTED,
        occurred_at=datetime.now(UTC),
        software_version=main.__version__,
        detail={"phenomenon": expected.phenomenon},
    )
    succeeded = attempted.model_copy(
        update={
            "event_id": uuid4(),
            "result": MutationResult.SUCCEEDED,
            "detail": {
                "phenomenon": expected.phenomenon,
                "content_digest": sha256_digest(expected.model_dump_json().encode()),
            },
        }
    )
    main.audit_store.append(attempted)
    main.audit_store.prepare_terminal(succeeded)

    main._reconcile_pending_audit()

    assert list(main.audit_store.iter_events()) == [attempted]
    assert list(main.audit_store.pending_events()) == [succeeded]


def test_restart_checks_latest_model_cycle_state_before_publishing_success(
    tmp_path,
    monkeypatch,
) -> None:
    isolated_client(tmp_path, monkeypatch)
    field = ModelCycleField(
        variable="air_temperature",
        level_type="surface",
        grid="global-0.25-degree",
        lead_hours=0,
    )
    expected = ModelGuidanceCycle(
        model_id="gfs",
        model_version="v16",
        guidance_origin=GuidanceOrigin.IMPORTED,
        initialized_at=datetime(2026, 8, 13, tzinfo=UTC),
        source_revision="revision-1",
        grids=[field.grid],
        expected_fields=[field],
        available_fields=[field],
    )
    conflicting_latest = expected.model_copy(update={"available_fields": []})
    main.model_catalog.register(expected)
    main.model_catalog.register(conflicting_latest)
    resource_id = str(main._core._cycle_summary(expected)["id"])
    attempted = MutationAuditEvent(
        event_id=uuid4(),
        request_id=uuid4(),
        actor="operator@example.invalid",
        action="model_cycle.catalogued",
        resource_type="model_cycle",
        resource_id=resource_id,
        result=MutationResult.ATTEMPTED,
        occurred_at=datetime.now(UTC),
        software_version=main.__version__,
        detail={"guidance_origin": GuidanceOrigin.IMPORTED.value},
    )
    succeeded = attempted.model_copy(
        update={
            "event_id": uuid4(),
            "result": MutationResult.SUCCEEDED,
            "detail": {
                "guidance_origin": GuidanceOrigin.IMPORTED.value,
                "content_digest": sha256_digest(expected.model_dump_json().encode()),
            },
        }
    )
    main.audit_store.append(attempted)
    main.audit_store.prepare_terminal(succeeded)

    main._reconcile_pending_audit()

    assert list(main.audit_store.iter_events()) == [attempted]
    assert list(main.audit_store.pending_events()) == [succeeded]


def test_restart_does_not_use_an_identical_prior_cycle_for_a_new_request(
    tmp_path,
    monkeypatch,
) -> None:
    isolated_client(tmp_path, monkeypatch)
    field = ModelCycleField(
        variable="air_temperature",
        level_type="surface",
        grid="global-0.25-degree",
        lead_hours=0,
    )
    expected = ModelGuidanceCycle(
        model_id="gfs",
        model_version="v16",
        guidance_origin=GuidanceOrigin.IMPORTED,
        initialized_at=datetime(2026, 8, 13, tzinfo=UTC),
        source_revision="revision-1",
        grids=[field.grid],
        expected_fields=[field],
        available_fields=[field],
    )
    main.model_catalog.register(expected)
    resource_id = str(main._core._cycle_summary(expected)["id"])
    attempted = MutationAuditEvent(
        event_id=uuid4(),
        request_id=uuid4(),
        actor="operator@example.invalid",
        action="model_cycle.catalogued",
        resource_type="model_cycle",
        resource_id=resource_id,
        result=MutationResult.ATTEMPTED,
        occurred_at=datetime.now(UTC),
        software_version=main.__version__,
        detail={"guidance_origin": GuidanceOrigin.IMPORTED.value},
    )
    succeeded = attempted.model_copy(
        update={
            "event_id": uuid4(),
            "result": MutationResult.SUCCEEDED,
            "detail": {
                "guidance_origin": GuidanceOrigin.IMPORTED.value,
                "content_digest": sha256_digest(expected.model_dump_json().encode()),
            },
        }
    )
    main.audit_store.append(attempted)
    main.audit_store.prepare_terminal(succeeded)

    main._reconcile_pending_audit()

    assert list(main.audit_store.iter_events()) == [attempted]
    assert list(main.audit_store.pending_events()) == [succeeded]


def test_decode_failure_audits_retained_source_evidence(tmp_path, monkeypatch) -> None:
    client, _ = isolated_client(tmp_path, monkeypatch)
    payload = b"not a decodable observation"
    digest = sha256_digest(payload)

    response = client.post("/v1/source-records", content=payload)

    assert response.status_code == 422
    assert main.raw_store.retrieve(digest) == payload
    attempted, failed = main.audit_store.iter_events()
    assert attempted.result == MutationResult.ATTEMPTED
    assert failed.result == MutationResult.FAILED
    assert failed.detail == {
        "error_type": "SourceDecodeError",
        "retained": True,
    }


def test_quality_rejection_audits_retained_source_evidence(tmp_path, monkeypatch) -> None:
    client, _ = isolated_client(tmp_path, monkeypatch)
    record = json.loads(
        (Path(__file__).resolve().parents[2] / "testdata/observations/temperature.json").read_text()
    )
    record["quality_disposition"] = "reject"
    payload = json.dumps(record).encode()
    digest = sha256_digest(payload)

    response = client.post("/v1/source-records", content=payload)

    assert response.status_code == 422
    assert main.raw_store.retrieve(digest) == payload
    attempted, failed = main.audit_store.iter_events()
    assert attempted.result == MutationResult.ATTEMPTED
    assert failed.result == MutationResult.FAILED
    assert failed.detail == {
        "error_type": "HTTPException",
        "retained": True,
    }


def test_canonical_conflict_audits_retained_source_evidence(tmp_path, monkeypatch) -> None:
    client, _ = isolated_client(tmp_path, monkeypatch)
    payload = (
        Path(__file__).resolve().parents[2] / "testdata/observations/temperature.json"
    ).read_bytes()
    digest = sha256_digest(payload)
    decoded = main.ingest_source_record(
        payload,
        adapter=main.adapter,
        raw_store=main.raw_store,
    ).observations[0]
    admitted = main._core._with_platform_verification(decoded)
    assert admitted.value is not None
    main.store.append(admitted.model_copy(update={"value": admitted.value + 1.0}))

    response = client.post("/v1/source-records", content=payload)

    assert response.status_code == 409
    assert main.raw_store.retrieve(digest) == payload
    attempted, failed = main.audit_store.iter_events()
    assert attempted.result == MutationResult.ATTEMPTED
    assert failed.result == MutationResult.FAILED
    assert failed.detail == {
        "error_type": "HTTPException",
        "retained": True,
    }


def test_raw_evidence_read_requires_service_identity_in_production(
    tmp_path,
    monkeypatch,
) -> None:
    client, credential = isolated_client(tmp_path, monkeypatch, production=True)
    assert credential is not None
    payload = b"protected source record"
    digest = sha256_digest(payload)
    headers = service_headers(credential)
    retention = client.put(
        f"/v1/source-records/{digest}",
        content=payload,
        headers=headers,
    )
    assert retention.status_code == 201

    assert client.get(f"/v1/source-records/{digest}").status_code == 401
    assert (
        client.get(
            f"/v1/source-records/{digest}",
            headers={"authorization": f"Bearer {credential}"},
        ).status_code
        == 401
    )
    response = client.get(f"/v1/source-records/{digest}", headers=headers)
    assert response.status_code == 200
    assert response.content == payload


def test_invalid_request_identifier_is_replaced_with_a_uuid(tmp_path, monkeypatch) -> None:
    client, _ = isolated_client(tmp_path, monkeypatch)
    response = client.get("/healthz", headers={"x-request-id": "not-a-uuid"})
    assert response.status_code == 200
    assert UUID(response.headers["x-request-id"])

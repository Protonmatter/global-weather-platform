from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from weather_platform.api import main
from weather_platform.config import Settings
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

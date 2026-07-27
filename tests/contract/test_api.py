import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from weather_platform.api import main
from weather_platform.config import Settings
from weather_platform.domain.models import Observation
from weather_platform.provenance import sha256_digest
from weather_platform.storage.jsonl import JsonlObservationStore
from weather_platform.storage.raw import RawSourceStore

ROOT = Path(__file__).resolve().parents[2]


def isolated_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(main, "store", JsonlObservationStore(tmp_path / "observations.jsonl"))
    monkeypatch.setattr(main, "raw_store", RawSourceStore(tmp_path / "raw"))
    return TestClient(main.app)


def test_observation_round_trip(tmp_path: Path, monkeypatch) -> None:
    client = isolated_client(tmp_path, monkeypatch)
    payload = (ROOT / "testdata/observations/temperature.json").read_bytes()
    digest = sha256_digest(payload)

    response = client.put(f"/v1/source-records/{digest}", content=payload)
    assert response.status_code == 201

    record = json.loads(payload)
    record["provenance"]["source_record_digest"] = digest
    response = client.post("/v1/observations", json=record)
    assert response.status_code == 202

    response = client.get("/v1/observations", params={"phenomenon": "air_temperature"})
    assert response.status_code == 200
    assert response.json()[0]["observation_id"] == record["observation_id"]


def test_observation_requires_retained_source_record(tmp_path: Path, monkeypatch) -> None:
    client = isolated_client(tmp_path, monkeypatch)
    record = json.loads((ROOT / "testdata/observations/temperature.json").read_text())

    response = client.post("/v1/observations", json=record)
    assert response.status_code == 422
    assert "retained source record" in response.json()["detail"]
    assert main.store.list() == []


def test_raw_deposit_is_idempotent_and_digest_checked(tmp_path: Path, monkeypatch) -> None:
    client = isolated_client(tmp_path, monkeypatch)
    payload = b'{"source": "external-decoder-record"}'
    digest = sha256_digest(payload)

    first = client.put(f"/v1/source-records/{digest}", content=payload)
    second = client.put(f"/v1/source-records/{digest}", content=payload)
    assert first.status_code == 201
    assert second.status_code == 200

    response = client.get(f"/v1/source-records/{digest}")
    assert response.content == payload

    mismatch = client.put(f"/v1/source-records/sha256:{'0' * 64}", content=payload)
    assert mismatch.status_code == 422
    assert "does not match" in mismatch.json()["detail"]


def test_health_discloses_control_state() -> None:
    client = TestClient(main.app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["telemetry_enabled"] is False
    assert response.json()["external_egress_enabled"] is False
    assert response.json()["max_source_record_bytes"] > 0
    assert response.json()["mutation_authentication_enabled"] is False


def test_production_mutations_require_service_and_operator_identity(
    tmp_path: Path, monkeypatch
) -> None:
    client = isolated_client(tmp_path, monkeypatch)
    token = "s" * 32
    monkeypatch.setattr(
        main,
        "settings",
        Settings(
            _env_file=None,
            environment="production",
            data_dir=tmp_path,
            control_plane_token=token,
        ),
    )
    payload = b'{"source":"authenticated-retention"}'
    digest = sha256_digest(payload)

    assert client.put(f"/v1/source-records/{digest}", content=payload).status_code == 401
    assert (
        client.put(
            f"/v1/source-records/{digest}",
            content=payload,
            headers={"x-weather-actor": "spoofed@example.invalid"},
        ).status_code
        == 401
    )
    response = client.put(
        f"/v1/source-records/{digest}",
        content=payload,
        headers={
            "authorization": f"Bearer {token}",
            "x-weather-actor": "operator@example.invalid",
        },
    )
    assert response.status_code == 201


def test_oversized_source_records_are_rejected_before_retention(
    tmp_path: Path, monkeypatch
) -> None:
    raw_store = RawSourceStore(tmp_path / "raw", max_record_bytes=8)
    monkeypatch.setattr(main, "raw_store", raw_store)
    monkeypatch.setattr(main, "store", JsonlObservationStore(tmp_path / "observations.jsonl"))
    client = TestClient(main.app)
    payload = b"123456789"
    digest = sha256_digest(payload)

    for method, path in (
        ("POST", "/v1/source-records"),
        ("PUT", f"/v1/source-records/{digest}"),
    ):
        response = client.request(method, path, content=payload)
        assert response.status_code == 413
        assert response.headers["content-type"].startswith("application/problem+json")
        assert "8-byte retention limit" in response.json()["detail"]
        assert list(raw_store.root.iterdir()) == []


def test_streamed_source_record_limit_does_not_trust_content_length(
    tmp_path: Path, monkeypatch
) -> None:
    raw_store = RawSourceStore(tmp_path / "raw", max_record_bytes=8)
    monkeypatch.setattr(main, "raw_store", raw_store)
    messages = iter(
        [
            {"type": "http.request", "body": b"1234", "more_body": True},
            {"type": "http.request", "body": b"56789", "more_body": False},
        ]
    )

    async def receive() -> dict[str, object]:
        return next(messages)

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/source-records",
            "headers": [(b"content-length", b"1")],
        },
        receive,
    )

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(main._read_bounded_source_record(request))

    assert excinfo.value.status_code == 413
    assert list(raw_store.root.iterdir()) == []


def test_rejected_observation_is_not_stored(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main, "store", JsonlObservationStore(tmp_path / "observations.jsonl"))
    client = TestClient(main.app)
    record = json.loads((ROOT / "testdata/observations/temperature.json").read_text())
    record["quality_disposition"] = "reject"
    response = client.post("/v1/observations", json=record)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 422
    assert "rejected observations" in response.json()["detail"]
    assert main.store.list() == []


def test_problem_details_for_invalid_store_limit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main, "store", JsonlObservationStore(tmp_path / "observations.jsonl"))
    client = TestClient(main.app)
    response = client.get("/v1/observations", params={"limit": 10001})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "urn:weather:problem:invalid-request"


def test_source_record_ingestion_round_trip(tmp_path: Path, monkeypatch) -> None:
    client = isolated_client(tmp_path, monkeypatch)
    payload = (ROOT / "testdata/observations/temperature.json").read_bytes()

    response = client.post("/v1/source-records", content=payload)
    assert response.status_code == 202
    digest = response.json()["source_record_digest"]
    assert digest == sha256_digest(payload)

    response = client.get(f"/v1/source-records/{digest}")
    assert response.status_code == 200
    assert response.content == payload

    response = client.get("/v1/observations")
    assert response.status_code == 200
    assert response.json()[0]["provenance"]["source_record_digest"] == digest


def test_corrected_source_record_becomes_a_new_record(tmp_path: Path, monkeypatch) -> None:
    client = isolated_client(tmp_path, monkeypatch)
    payload = (ROOT / "testdata/observations/temperature.json").read_bytes()
    first = client.post("/v1/source-records", content=payload)
    assert first.status_code == 202

    # Different bytes decode to a different source digest, so the derived id
    # differs and the corrected report is retained as a distinct record rather
    # than conflicting with the original.
    corrected = json.loads(payload)
    corrected["value"] = 999.0
    second = client.post("/v1/source-records", content=json.dumps(corrected).encode("utf-8"))
    assert second.status_code == 202
    ids = {first.json()["observation_ids"][0], second.json()["observation_ids"][0]}
    assert len(ids) == 2
    assert len(main.store.list()) == 2


def test_conflicting_direct_observation_is_rejected(tmp_path: Path, monkeypatch) -> None:
    client = isolated_client(tmp_path, monkeypatch)
    payload = (ROOT / "testdata/observations/temperature.json").read_bytes()
    digest = sha256_digest(payload)
    assert client.put(f"/v1/source-records/{digest}", content=payload).status_code == 201

    record = json.loads(payload)
    record["provenance"]["source_record_digest"] = digest
    assert client.post("/v1/observations", json=record).status_code == 202
    assert client.post("/v1/observations", json=record).status_code == 202

    # Availability timestamps can differ when an authenticated BFF retries the
    # same canonical content; the first admitted timestamps remain authoritative.
    record["ingestion_time"] = "2026-07-20T18:02:03Z"
    record["provenance"]["ingested_at"] = "2026-07-20T18:02:03Z"
    assert client.post("/v1/observations", json=record).status_code == 202

    record["value"] = 999.0
    response = client.post("/v1/observations", json=record)
    assert response.status_code == 409
    assert len(main.store.list()) == 1


def test_conflicting_batch_leaves_store_unmutated(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main, "store", JsonlObservationStore(tmp_path / "observations.jsonl"))
    payload = (ROOT / "testdata/observations/temperature.json").read_bytes()
    base = Observation.model_validate_json(payload)
    main._admit_observations([base])

    fresh = base.model_copy(update={"observation_id": UUID(int=1)})
    conflicting = base.model_copy(update={"value": 999.0})
    with pytest.raises(HTTPException) as excinfo:
        main._admit_observations([fresh, conflicting])
    assert excinfo.value.status_code == 409
    assert main.store.list() == [base]


def test_quarantined_observation_is_retained_but_not_served_by_default(
    tmp_path: Path, monkeypatch
) -> None:
    client = isolated_client(tmp_path, monkeypatch)
    payload = (ROOT / "testdata/observations/temperature.json").read_bytes()
    quarantined = json.loads(payload)
    quarantined["quality_disposition"] = "quarantine"
    quarantined["quality_flags"] = ["range_suspect"]

    response = client.post("/v1/source-records", content=json.dumps(quarantined).encode("utf-8"))
    assert response.status_code == 202

    # Retained and stored, but excluded from the default serving path.
    assert client.get("/v1/observations").json() == []
    included = client.get("/v1/observations", params={"include_quarantined": True})
    assert len(included.json()) == 1
    assert included.json()[0]["quality_disposition"] == "quarantine"


def test_http_exception_headers_are_preserved() -> None:
    client = TestClient(main.app)
    response = client.request("DELETE", "/healthz")
    assert response.status_code == 405
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "GET" in response.headers["allow"]


def test_tampered_retained_source_blocks_admission(tmp_path: Path, monkeypatch) -> None:
    client = isolated_client(tmp_path, monkeypatch)
    payload = (ROOT / "testdata/observations/temperature.json").read_bytes()
    digest = sha256_digest(payload)
    assert client.put(f"/v1/source-records/{digest}", content=payload).status_code == 201

    record_path = tmp_path / "raw" / digest.removeprefix("sha256:")
    record_path.chmod(0o640)
    record_path.write_bytes(b"tampered")

    record = json.loads(payload)
    record["provenance"]["source_record_digest"] = digest
    response = client.post("/v1/observations", json=record)
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "urn:weather:problem:internal-error"
    assert main.store.list() == []


def test_source_record_retry_does_not_duplicate_observations(tmp_path: Path, monkeypatch) -> None:
    client = isolated_client(tmp_path, monkeypatch)
    payload = (ROOT / "testdata/observations/temperature.json").read_bytes()

    first = client.post("/v1/source-records", content=payload)
    second = client.post("/v1/source-records", content=payload)
    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json() == first.json()
    assert len(main.store.list()) == 1


def test_concurrent_source_record_retries_do_not_duplicate(tmp_path: Path, monkeypatch) -> None:
    client = isolated_client(tmp_path, monkeypatch)
    payload = (ROOT / "testdata/observations/temperature.json").read_bytes()

    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(
            pool.map(lambda _: client.post("/v1/source-records", content=payload), range(5))
        )
    assert all(response.status_code == 202 for response in responses)
    assert len(main.store.list()) == 1


def test_unexpected_fault_returns_problem_details(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main, "store", JsonlObservationStore(tmp_path / "observations.jsonl"))

    def broken_list(phenomenon: str | None = None, limit: int = 100) -> list:
        raise OSError("disk failure")

    monkeypatch.setattr(main.store, "list", broken_list)
    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.get("/v1/observations")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == "unexpected internal error"


def test_undecodable_source_record_is_retained_and_rejected(tmp_path: Path, monkeypatch) -> None:
    client = isolated_client(tmp_path, monkeypatch)
    payload = b"not-a-canonical-observation"

    response = client.post("/v1/source-records", content=payload)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")

    response = client.get(f"/v1/source-records/{sha256_digest(payload)}")
    assert response.status_code == 200
    assert response.content == payload
    assert main.store.list() == []


def test_empty_source_record_is_rejected(tmp_path: Path, monkeypatch) -> None:
    client = isolated_client(tmp_path, monkeypatch)
    response = client.post("/v1/source-records", content=b"")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


def test_unknown_source_record_is_not_found(tmp_path: Path, monkeypatch) -> None:
    client = isolated_client(tmp_path, monkeypatch)
    response = client.get(f"/v1/source-records/sha256:{'0' * 64}")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    response = client.get("/v1/source-records/not-a-digest")
    assert response.status_code == 422
    assert response.json()["type"] == "urn:weather:problem:invalid-request"


def test_corrupt_store_is_reported_as_internal_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main, "store", JsonlObservationStore(tmp_path / "observations.jsonl"))
    (tmp_path / "observations.jsonl").write_text("not-json\n", encoding="utf-8")
    client = TestClient(main.app)
    response = client.get("/v1/observations")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "urn:weather:problem:internal-error"

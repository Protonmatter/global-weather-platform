import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from weather_platform.api import main
from weather_platform.provenance import sha256_digest
from weather_platform.storage.jsonl import JsonlObservationStore
from weather_platform.storage.raw import RawSourceStore

ROOT = Path(__file__).resolve().parents[2]


def isolated_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(main, "store", JsonlObservationStore(tmp_path / "observations.jsonl"))
    monkeypatch.setattr(main, "raw_store", RawSourceStore(tmp_path / "raw"))
    return TestClient(main.app)


def test_observation_round_trip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main, "store", JsonlObservationStore(tmp_path / "observations.jsonl"))
    client = TestClient(main.app)
    record = json.loads((ROOT / "testdata/observations/temperature.json").read_text())

    response = client.post("/v1/observations", json=record)
    assert response.status_code == 202

    response = client.get("/v1/observations", params={"phenomenon": "air_temperature"})
    assert response.status_code == 200
    assert response.json()[0]["observation_id"] == record["observation_id"]


def test_health_discloses_control_state() -> None:
    client = TestClient(main.app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["telemetry_enabled"] is False
    assert response.json()["external_egress_enabled"] is False


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

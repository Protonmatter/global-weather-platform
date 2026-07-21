import json
from pathlib import Path

from fastapi.testclient import TestClient

from weather_platform.api import main
from weather_platform.ingestion.service import IngestionService
from weather_platform.storage.jsonl import JsonlObservationStore
from weather_platform.storage.raw_objects import FileSystemRawObjectStore

ROOT = Path(__file__).resolve().parents[2]


def configure_test_stores(
    tmp_path: Path, monkeypatch
) -> tuple[JsonlObservationStore, FileSystemRawObjectStore]:
    observation_store = JsonlObservationStore(tmp_path / "observations.jsonl")
    raw_store = FileSystemRawObjectStore(tmp_path / "raw")
    service = IngestionService(raw_store, observation_store)
    monkeypatch.setattr(main, "store", observation_store)
    monkeypatch.setattr(main, "raw_store", raw_store)
    monkeypatch.setattr(main, "ingestion_service", service)
    return observation_store, raw_store


def test_observation_round_trip_retains_exact_source(tmp_path: Path, monkeypatch) -> None:
    observation_store, raw_store = configure_test_stores(tmp_path, monkeypatch)
    client = TestClient(main.app)
    payload = (ROOT / "testdata/observations/temperature.json").read_bytes()

    response = client.post(
        "/v1/observations",
        content=payload,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["observations_written"] == 1
    assert body["duplicate"] is False
    assert raw_store.get(body["raw_object_digest"]) == payload

    response = client.get("/v1/observations", params={"phenomenon": "air_temperature"})
    assert response.status_code == 200
    observation = response.json()[0]
    assert observation["observation_id"] == body["observation_ids"][0]
    assert observation["provenance"]["source_object_uri"] == body["raw_object_uri"]
    assert len(observation_store.list()) == 1


def test_duplicate_post_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    observation_store, _ = configure_test_stores(tmp_path, monkeypatch)
    client = TestClient(main.app)
    record = json.loads((ROOT / "testdata/observations/temperature.json").read_text())

    first = client.post("/v1/observations", json=record)
    second = client.post("/v1/observations", json=record)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["observation_ids"] == second.json()["observation_ids"]
    assert second.json()["duplicate"] is True
    assert second.json()["observations_written"] == 0
    assert len(observation_store.list()) == 1


def test_health_discloses_control_state() -> None:
    client = TestClient(main.app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["telemetry_enabled"] is False
    assert response.json()["external_egress_enabled"] is False
    assert response.json()["raw_object_store"] == "filesystem-sha256"


def test_rejected_observation_is_not_stored_but_raw_is_retained(
    tmp_path: Path, monkeypatch
) -> None:
    observation_store, raw_store = configure_test_stores(tmp_path, monkeypatch)
    client = TestClient(main.app)
    record = json.loads((ROOT / "testdata/observations/temperature.json").read_text())
    record["quality_disposition"] = "reject"
    response = client.post("/v1/observations", json=record)
    assert response.status_code == 422
    assert observation_store.list() == []
    assert any(path.is_file() for path in (raw_store.root / "sha256").rglob("*"))


def test_problem_details_for_invalid_store_limit(tmp_path: Path, monkeypatch) -> None:
    configure_test_stores(tmp_path, monkeypatch)
    client = TestClient(main.app)
    response = client.get("/v1/observations", params={"limit": 10001})
    assert response.status_code == 422


def test_ingestion_requires_json_content_type(tmp_path: Path, monkeypatch) -> None:
    configure_test_stores(tmp_path, monkeypatch)
    client = TestClient(main.app)
    response = client.post(
        "/v1/observations", content=b"{}", headers={"content-type": "text/plain"}
    )
    assert response.status_code == 415


def test_ingestion_rejects_empty_source_record(tmp_path: Path, monkeypatch) -> None:
    configure_test_stores(tmp_path, monkeypatch)
    client = TestClient(main.app)
    response = client.post(
        "/v1/observations",
        content=b"",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")

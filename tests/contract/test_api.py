import json
from pathlib import Path

from fastapi.testclient import TestClient

from weather_platform.api import main
from weather_platform.storage.jsonl import JsonlObservationStore

ROOT = Path(__file__).resolve().parents[2]


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


def test_corrupt_store_is_reported_as_internal_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main, "store", JsonlObservationStore(tmp_path / "observations.jsonl"))
    (tmp_path / "observations.jsonl").write_text("not-json\n", encoding="utf-8")
    client = TestClient(main.app)
    response = client.get("/v1/observations")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "urn:weather:problem:internal-error"

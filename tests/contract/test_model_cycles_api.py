from pathlib import Path

from fastapi.testclient import TestClient

from weather_platform.api import main
from weather_platform.storage.model_catalog_store import ModelGuidanceCatalog

FIELD = {
    "variable": "temperature",
    "level_type": "isobaric",
    "level_value": 850.0,
    "grid": "0p25",
    "lead_hours": 0,
}


def catalog_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(
        main, "model_catalog", ModelGuidanceCatalog(tmp_path / "model-cycles.jsonl")
    )
    return TestClient(main.app)


def cycle(origin: str, model_id: str = "gfs", available: list | None = None) -> dict:
    return {
        "model_id": model_id,
        "model_version": "v16.3",
        "guidance_origin": origin,
        "initialized_at": "2026-07-22T00:00:00Z",
        "source_revision": "2026072200",
        "grids": ["0p25"],
        "expected_fields": [FIELD, {**FIELD, "lead_hours": 6}],
        "available_fields": available
        if available is not None
        else [FIELD, {**FIELD, "lead_hours": 6}],
    }


def test_four_way_guidance_distinction_is_queryable(tmp_path: Path, monkeypatch) -> None:
    client = catalog_client(tmp_path, monkeypatch)
    origins = ["imported", "platform", "official_warning", "experimental"]
    for index, origin in enumerate(origins):
        response = client.post("/v1/model-cycles", json=cycle(origin, model_id=f"model-{index}"))
        assert response.status_code == 202
        assert response.json()["guidance_origin"] == origin

    assert len(client.get("/v1/model-cycles").json()) == 4
    for origin in origins:
        filtered = client.get("/v1/model-cycles", params={"guidance_origin": origin}).json()
        assert [entry["guidance_origin"] for entry in filtered] == [origin]


def test_unlabeled_guidance_is_rejected(tmp_path: Path, monkeypatch) -> None:
    client = catalog_client(tmp_path, monkeypatch)
    payload = cycle("imported")
    del payload["guidance_origin"]
    response = client.post("/v1/model-cycles", json=payload)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


def test_partial_and_missing_cycles_are_explicit(tmp_path: Path, monkeypatch) -> None:
    client = catalog_client(tmp_path, monkeypatch)

    partial = client.post("/v1/model-cycles", json=cycle("imported", available=[FIELD]))
    assert partial.json()["completeness"] == "partial"
    assert partial.json()["missing_field_count"] == 1
    assert partial.json()["available_field_count"] == 1
    assert partial.json()["expected_field_count"] == 2
    assert partial.json()["id"]
    assert partial.json()["updated_at"] == "2026-07-22T00:00:00+00:00"

    missing = client.post("/v1/model-cycles", json=cycle("imported", model_id="gefs", available=[]))
    assert missing.json()["completeness"] == "missing"
    assert missing.json()["missing_field_count"] == 2

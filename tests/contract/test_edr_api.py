import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from weather_platform.api import main
from weather_platform.domain.models import Observation
from weather_platform.storage.jsonl import JsonlObservationStore

ROOT = Path(__file__).resolve().parents[2]


def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(main, "store", JsonlObservationStore(tmp_path / "observations.jsonl"))
    return TestClient(main.app)


def seed(
    *,
    lon: float,
    lat: float,
    phenomenon: str = "air_temperature",
    observed: str = "2026-07-20T18:00:00Z",
    disposition: str = "accept",
    flags: list[str] | None = None,
) -> None:
    record = json.loads((ROOT / "testdata/observations/temperature.json").read_text())
    record["observation_id"] = str(uuid4())
    record["geometry"] = {"type": "Point", "coordinates": [lon, lat]}
    record["phenomenon"] = phenomenon
    record["observation_time"] = observed
    record["quality_disposition"] = disposition
    record["quality_flags"] = flags or []
    main.store.append(Observation.model_validate(record))


def test_collections_lists_the_observations_collection(tmp_path, monkeypatch) -> None:
    c = client(tmp_path, monkeypatch)
    body = c.get("/v1/edr/collections").json()
    assert [entry["id"] for entry in body["collections"]] == ["observations"]


def test_position_returns_nearby_observations_with_provenance(tmp_path, monkeypatch) -> None:
    c = client(tmp_path, monkeypatch)
    seed(lon=-74.006, lat=40.7128)
    seed(lon=0.0, lat=0.0)  # far away

    response = c.get(
        "/v1/edr/collections/observations/position",
        params={"coords": "POINT(-74.006 40.7128)", "within_degrees": 0.5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 1
    props = body["features"][0]["properties"]
    assert props["unit"] == "K"
    assert props["valid_time"] == "2026-07-20T18:00:00+00:00"
    assert props["issued_at"] == "2026-07-20T18:01:03+00:00"
    assert props["provenance"]["source_record_digest"].startswith("sha256:")


def test_position_datetime_subsetting(tmp_path, monkeypatch) -> None:
    c = client(tmp_path, monkeypatch)
    seed(lon=10.0, lat=20.0, observed="2026-07-20T00:00:00Z")
    seed(lon=10.0, lat=20.0, observed="2026-07-21T12:00:00Z")

    response = c.get(
        "/v1/edr/collections/observations/position",
        params={
            "coords": "POINT(10 20)",
            "datetime": "2026-07-20T00:00:00Z/2026-07-20T23:59:59Z",
        },
    )
    times = [f["properties"]["valid_time"] for f in response.json()["features"]]
    assert times == ["2026-07-20T00:00:00+00:00"]


def test_position_matches_across_the_antimeridian(tmp_path, monkeypatch) -> None:
    c = client(tmp_path, monkeypatch)
    seed(lon=179.9, lat=0.0)

    response = c.get(
        "/v1/edr/collections/observations/position",
        params={"coords": "POINT(-179.9 0)", "within_degrees": 0.5},
    )
    assert len(response.json()["features"]) == 1


def test_position_parameter_name_filter(tmp_path, monkeypatch) -> None:
    c = client(tmp_path, monkeypatch)
    seed(lon=10.0, lat=20.0, phenomenon="air_temperature")
    seed(lon=10.0, lat=20.0, phenomenon="wind_speed")

    response = c.get(
        "/v1/edr/collections/observations/position",
        params={"coords": "POINT(10 20)", "parameter-name": "wind_speed"},
    )
    phenomena = {f["properties"]["phenomenon"] for f in response.json()["features"]}
    assert phenomena == {"wind_speed"}


def test_position_excludes_quarantined_by_default(tmp_path, monkeypatch) -> None:
    c = client(tmp_path, monkeypatch)
    seed(lon=10.0, lat=20.0, disposition="quarantine", flags=["range_suspect"])

    default = c.get("/v1/edr/collections/observations/position", params={"coords": "POINT(10 20)"})
    assert default.json()["features"] == []
    included = c.get(
        "/v1/edr/collections/observations/position",
        params={"coords": "POINT(10 20)", "include_quarantined": True},
    )
    assert len(included.json()["features"]) == 1


def test_position_malformed_coords_is_client_error(tmp_path, monkeypatch) -> None:
    c = client(tmp_path, monkeypatch)
    response = c.get("/v1/edr/collections/observations/position", params={"coords": "not-a-point"})
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")

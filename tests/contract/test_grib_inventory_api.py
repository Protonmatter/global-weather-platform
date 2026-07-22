import pytest

eccodes = pytest.importorskip("eccodes")

from fastapi.testclient import TestClient  # noqa: E402

from weather_platform.api import main  # noqa: E402


def _grib2(short_name: str, level: int, step: int) -> bytes:
    gid = eccodes.codes_grib_new_from_samples("GRIB2")
    eccodes.codes_set(gid, "shortName", short_name)
    eccodes.codes_set(gid, "typeOfLevel", "isobaricInhPa")
    eccodes.codes_set(gid, "level", level)
    eccodes.codes_set(gid, "step", step)
    message = eccodes.codes_get_message(gid)
    eccodes.codes_release(gid)
    return message


def test_grib_inventory_endpoint_decodes_uploaded_bytes() -> None:
    client = TestClient(main.app)
    response = client.post("/v1/decode/grib-inventory", content=_grib2("t", 850, 6))
    assert response.status_code == 200
    body = response.json()
    assert body["decoder_version"].startswith("grib-field-decoder/")
    assert body["fields"][0]["variable"] == "t"
    assert body["fields"][0]["lead_hours"] == 6
    assert body["fields"][0]["level_value"] == 850.0


def test_grib_inventory_endpoint_rejects_malformed() -> None:
    client = TestClient(main.app)
    response = client.post("/v1/decode/grib-inventory", content=b"not-a-grib")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")

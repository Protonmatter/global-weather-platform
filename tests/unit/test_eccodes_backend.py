import pytest

eccodes = pytest.importorskip("eccodes")

from weather_platform.ingestion.eccodes_backend import (  # noqa: E402
    grib_field_inventory,
    runtime_decoder_version,
)


def _grib2(short_name: str, level: int, step: int) -> bytes:
    gid = eccodes.codes_grib_new_from_samples("GRIB2")
    eccodes.codes_set(gid, "shortName", short_name)
    eccodes.codes_set(gid, "typeOfLevel", "isobaricInhPa")
    eccodes.codes_set(gid, "level", level)
    eccodes.codes_set(gid, "step", step)
    message = eccodes.codes_get_message(gid)
    eccodes.codes_release(gid)
    return message


def test_runtime_decoder_version_reports_real_eccodes() -> None:
    version = runtime_decoder_version()
    assert version.startswith("grib-field-decoder/")
    assert "eccodes/" in version


def test_grib_field_inventory_decodes_real_messages() -> None:
    payload = _grib2("t", 850, 6) + _grib2("u", 500, 12)
    fields = grib_field_inventory(payload)
    assert len(fields) == 2
    by_variable = {field.variable: field for field in fields}
    assert by_variable["t"].level_value == 850.0
    assert by_variable["t"].level_type == "isobaricInhPa"
    assert by_variable["t"].lead_hours == 6
    assert by_variable["u"].lead_hours == 12
    assert by_variable["u"].grid.startswith("regular_ll:")


def test_malformed_grib_is_rejected() -> None:
    with pytest.raises(ValueError, match="GRIB2"):
        grib_field_inventory(b"not-a-grib-message")

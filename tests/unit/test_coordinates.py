import math

import pytest

from weather_platform.grids.coordinates import normalize_longitude, wrapped_longitude_distance


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.0, 0.0),
        (180.0, -180.0),
        (-180.0, -180.0),
        (181.0, -179.0),
        (-181.0, 179.0),
        (360.0, 0.0),
        (540.0, -180.0),
    ],
)
def test_normalize_longitude_uses_geojson_range(value: float, expected: float) -> None:
    assert normalize_longitude(value) == expected


def test_normalization_is_idempotent() -> None:
    for value in range(-1080, 1081, 7):
        normalized = normalize_longitude(float(value))
        assert normalize_longitude(normalized) == normalized
        assert -180.0 <= normalized < 180.0


def test_wrapped_distance_handles_antimeridian() -> None:
    assert wrapped_longitude_distance(179.9, -179.9) == pytest.approx(0.2)
    assert wrapped_longitude_distance(10.0, 350.0) == pytest.approx(20.0)
    assert wrapped_longitude_distance(-180.0, 0.0) == pytest.approx(180.0)


def test_wrapped_distance_handles_extreme_finite_inputs_without_overflow() -> None:
    assert wrapped_longitude_distance(1e308, -1e308) == pytest.approx(128.0)


def test_coordinate_functions_reject_non_finite_values() -> None:
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="finite"):
            normalize_longitude(value)
        with pytest.raises(ValueError, match="finite"):
            wrapped_longitude_distance(0.0, value)

import math

import pytest

from weather_platform.grids.wind import meteorological_direction_to_uv


@pytest.mark.parametrize(
    ("degrees_from", "expected_u", "expected_v"),
    [
        (0.0, 0.0, -10.0),
        (90.0, -10.0, 0.0),
        (180.0, 0.0, 10.0),
        (270.0, 10.0, 0.0),
        (360.0, 0.0, -10.0),
    ],
)
def test_cardinal_meteorological_directions_point_toward_motion(
    degrees_from: float,
    expected_u: float,
    expected_v: float,
) -> None:
    u, v = meteorological_direction_to_uv(10.0, degrees_from)
    assert u == pytest.approx(expected_u, abs=1e-12)
    assert v == pytest.approx(expected_v, abs=1e-12)


def test_zero_speed_has_zero_components_for_any_direction() -> None:
    assert meteorological_direction_to_uv(0.0, 123.0) == pytest.approx((0.0, 0.0))


def test_direction_wraps_without_changing_vector() -> None:
    assert meteorological_direction_to_uv(12.0, -90.0) == pytest.approx(
        meteorological_direction_to_uv(12.0, 270.0)
    )


def test_negative_speed_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        meteorological_direction_to_uv(-1.0, 0.0)


def test_non_finite_inputs_are_rejected() -> None:
    for speed, direction in ((math.nan, 0.0), (1.0, math.inf), (math.inf, 0.0)):
        with pytest.raises(ValueError, match="finite"):
            meteorological_direction_to_uv(speed, direction)

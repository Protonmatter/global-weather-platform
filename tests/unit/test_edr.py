from datetime import UTC, datetime

import pytest

from weather_platform.api.edr import (
    angular_distance_degrees,
    parse_datetime_interval,
    parse_position_coords,
)


def test_parse_position_coords() -> None:
    assert parse_position_coords("POINT(-74.006 40.7128)") == (-74.006, 40.7128)
    assert parse_position_coords("  point( 10 20 ) ") == (10.0, 20.0)
    for bad in ("74,40", "POINT(200 0)", "POINT(0 100)", "LINESTRING(0 0)"):
        with pytest.raises(ValueError):
            parse_position_coords(bad)


def test_parse_datetime_interval() -> None:
    assert parse_datetime_interval(None) == (None, None)
    instant = datetime(2026, 7, 20, 18, 0, tzinfo=UTC)
    assert parse_datetime_interval("2026-07-20T18:00:00Z") == (instant, instant)
    start = datetime(2026, 7, 20, tzinfo=UTC)
    end = datetime(2026, 7, 21, tzinfo=UTC)
    assert parse_datetime_interval("2026-07-20T00:00:00Z/2026-07-21T00:00:00Z") == (start, end)
    assert parse_datetime_interval("../2026-07-21T00:00:00Z") == (None, end)
    assert parse_datetime_interval("2026-07-20T00:00:00Z/..") == (start, None)
    with pytest.raises(ValueError, match="must not precede"):
        parse_datetime_interval("2026-07-21T00:00:00Z/2026-07-20T00:00:00Z")


def test_angular_distance_wraps_the_antimeridian() -> None:
    # 179.9 and -179.9 are 0.2 deg apart, not 359.8.
    assert angular_distance_degrees(179.9, 0.0, -179.9, 0.0) == pytest.approx(0.2)
    assert angular_distance_degrees(0.0, 0.0, 3.0, 4.0) == pytest.approx(5.0)

import math


def _require_finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def normalize_longitude(longitude: float) -> float:
    """Normalize longitude into the GeoJSON interval [-180, 180)."""

    _require_finite(longitude, "longitude")
    normalized = ((longitude + 180.0) % 360.0) - 180.0
    return 0.0 if normalized == 0.0 else normalized


def wrapped_longitude_distance(first: float, second: float) -> float:
    """Return the shortest angular distance between longitudes in degrees."""

    _require_finite(first, "first longitude")
    _require_finite(second, "second longitude")
    return abs(normalize_longitude(first - second))

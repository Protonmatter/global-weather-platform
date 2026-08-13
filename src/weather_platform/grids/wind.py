import math


def meteorological_direction_to_uv(speed: float, degrees_from: float) -> tuple[float, float]:
    """Convert speed and source direction into eastward and northward components.

    Meteorological direction reports where wind comes from, while U and V
    components report motion toward east and north respectively.
    """

    if not math.isfinite(speed) or not math.isfinite(degrees_from):
        raise ValueError("wind speed and direction must be finite")
    if speed < 0:
        raise ValueError("wind speed must be non-negative")

    radians = math.radians(degrees_from % 360.0)
    u = -speed * math.sin(radians)
    v = -speed * math.cos(radians)
    if abs(u) < 1e-15:
        u = 0.0
    if abs(v) < 1e-15:
        v = 0.0
    return u, v

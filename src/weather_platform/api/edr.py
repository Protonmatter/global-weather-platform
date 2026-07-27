"""OGC API - Environmental Data Retrieval (EDR) query helpers.

This slice implements the EDR ``position`` query over discrete point
observations. A position query samples data at a coordinate; for discrete
observations we return records within an angular tolerance of the point.
Longitude differences are wrapped, so a query near the antimeridian matches
observations on the other side of +/-180 rather than treating them as ~360
degrees away.
"""

import math
import re
from collections.abc import Iterable
from datetime import datetime

from pydantic import AwareDatetime, TypeAdapter

from weather_platform.domain.models import Observation

_WKT_POINT = re.compile(
    r"^\s*POINT\s*\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)\s*$",
    re.IGNORECASE,
)
_DATETIME = TypeAdapter(AwareDatetime)


def parse_position_coords(coords: str) -> tuple[float, float]:
    """Parse a WKT ``POINT(lon lat)`` into (longitude, latitude)."""
    match = _WKT_POINT.match(coords)
    if not match:
        raise ValueError("coords must be a WKT POINT(lon lat)")
    longitude, latitude = float(match.group(1)), float(match.group(2))
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be in [-180, 180]")
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be in [-90, 90]")
    return longitude, latitude


def parse_datetime_interval(
    value: str | None,
) -> tuple[datetime | None, datetime | None]:
    """Parse an OGC ``datetime`` parameter into a (start, end) interval.

    Accepts a single instant, or ``start/end`` where either bound may be ``..``
    to leave it open. Both bounds inclusive.
    """
    if value is None:
        return (None, None)
    if "/" not in value:
        instant = _DATETIME.validate_python(value)
        return (instant, instant)
    raw_start, _, raw_end = value.partition("/")
    start = None if raw_start in ("", "..") else _DATETIME.validate_python(raw_start)
    end = None if raw_end in ("", "..") else _DATETIME.validate_python(raw_end)
    if start is not None and end is not None and end < start:
        raise ValueError("datetime interval end must not precede start")
    return (start, end)


def angular_distance_degrees(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Return great-circle angular separation in degrees on a spherical Earth."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)
    cosine = math.sin(phi1) * math.sin(phi2) + math.cos(phi1) * math.cos(phi2) * math.cos(
        delta_lambda
    )
    return math.degrees(math.acos(min(1.0, max(-1.0, cosine))))


def observation_in_window(
    observation: Observation,
    start: datetime | None,
    end: datetime | None,
) -> bool:
    if start is not None and observation.observation_time < start:
        return False
    return not (end is not None and observation.observation_time > end)


def observation_to_feature(observation: Observation) -> dict[str, object]:
    """Render an observation as a GeoJSON Feature exposing units, provenance, and times."""
    provenance = observation.provenance
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": list(observation.geometry.coordinates),
        },
        "properties": {
            "phenomenon": observation.phenomenon,
            "value": observation.value,
            "unit": observation.unit,
            "uncertainty": observation.uncertainty,
            "quality_disposition": observation.quality_disposition.value,
            # Observations have no forecast issue time; expose the ingestion time
            # as the availability reference and observation_time as the valid time.
            "valid_time": observation.observation_time.isoformat(),
            "issued_at": observation.ingestion_time.isoformat(),
            "provenance": {
                "source_id": provenance.source_id,
                "source_record_digest": provenance.source_record_digest,
                "digest_verification": provenance.digest_verification.value,
                "decoder_version": provenance.decoder_version,
                "received_at": (
                    provenance.received_at.isoformat()
                    if provenance.received_at is not None
                    else None
                ),
                "ingested_at": provenance.ingested_at.isoformat(),
            },
        },
    }


def position_feature_collection(
    observations: Iterable[Observation],
    *,
    longitude: float,
    latitude: float,
    within_degrees: float,
    start: datetime | None,
    end: datetime | None,
    phenomena: set[str] | None,
    limit: int | None = None,
) -> dict[str, object]:
    features: list[dict[str, object]] = []
    for observation in observations:
        if phenomena is not None and observation.phenomenon not in phenomena:
            continue
        if not observation_in_window(observation, start, end):
            continue
        obs_lon, obs_lat = observation.geometry.coordinates[:2]
        if angular_distance_degrees(longitude, latitude, obs_lon, obs_lat) > within_degrees:
            continue
        features.append(observation_to_feature(observation))
        if limit is not None and len(features) >= limit:
            break
    return {"type": "FeatureCollection", "features": features}

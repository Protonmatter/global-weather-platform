from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from weather_platform.acquisition.noaa.gfs import GFS_COMPLETE_FIELDS, GFS_MINIMUM_FIELDS
from weather_platform.acquisition.noaa.grib_index import (
    AmbiguousFieldError,
    FieldRequirement,
    parse_grib_index,
    select_grib_messages,
)
from weather_platform.domain.cycle_lifecycle import (
    CycleFieldArrival,
    CycleProductScope,
    CycleState,
    evaluate_cycle,
)
from weather_platform.domain.grid_assets import GridFieldAsset, GridFieldProvenance
from weather_platform.domain.model_catalog import GuidanceOrigin
from weather_platform.domain.models import QualityDisposition
from weather_platform.grids.coordinates import wrapped_longitude_distance
from weather_platform.grids.wind import meteorological_direction_to_uv

INIT = datetime(2026, 8, 12, 18, 0, tzinfo=UTC)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
SCOPE = CycleProductScope(grid="gfs-0p25-global", lead_hours=6, member=None)


@pytest.mark.regression
@pytest.mark.scientific
def test_antimeridian_distance_remains_continuous() -> None:
    assert wrapped_longitude_distance(179.9, -179.9) == pytest.approx(0.2)


@pytest.mark.regression
@pytest.mark.scientific
def test_north_wind_is_not_rendered_as_northward_motion() -> None:
    u, v = meteorological_direction_to_uv(20.0, 0.0)
    assert u == pytest.approx(0.0)
    assert v < 0


@pytest.mark.regression
def test_duplicate_field_arrivals_do_not_publish_an_incomplete_cycle() -> None:
    publication = evaluate_cycle(
        [
            CycleFieldArrival(name="u_wind_10m", scope=SCOPE),
            CycleFieldArrival(name="u_wind_10m", scope=SCOPE),
            CycleFieldArrival(name="v_wind_10m", scope=SCOPE),
        ],
        scope=SCOPE,
        minimum_fields=GFS_MINIMUM_FIELDS,
        complete_fields=GFS_COMPLETE_FIELDS,
    )
    assert publication.state is CycleState.PARTIAL
    assert not publication.usable


@pytest.mark.regression
def test_forecast_hour_ambiguity_is_not_resolved_by_first_match() -> None:
    index = """1:0:d=2026081218:UGRD:10 m above ground:6 hour fcst:
2:100:d=2026081218:UGRD:10 m above ground:9 hour fcst:
"""
    entries = parse_grib_index(index, object_size=200)
    with pytest.raises(AmbiguousFieldError):
        select_grib_messages(
            entries,
            (FieldRequirement("u_wind_10m", ("UGRD", "10 m above ground")),),
        )


@pytest.mark.regression
@pytest.mark.scientific
def test_inconsistent_valid_time_cannot_enter_the_grid_catalog() -> None:
    provenance = GridFieldProvenance(
        source_id="noaa-gfs",
        source_record_digest=DIGEST_A,
        ingested_at=INIT + timedelta(minutes=1),
        decoder_version="grib-field-decoder/0.2.0+eccodes/2.38.3",
    )
    with pytest.raises(ValidationError, match="valid_at"):
        GridFieldAsset(
            asset_id=uuid4(),
            model_id="noaa-gfs",
            model_version="v16.3",
            guidance_origin=GuidanceOrigin.IMPORTED,
            initialized_at=INIT,
            valid_at=INIT + timedelta(hours=7),
            lead_seconds=21600,
            phenomenon="air_temperature",
            source_variable="2t",
            level_type="height_above_ground",
            level_value=2.0,
            level_unit="m",
            unit="K",
            grid_id="gfs-0p25-global",
            crs="OGC:CRS84",
            nx=1440,
            ny=721,
            longitude_convention="0_360",
            storage_encoding="zarr-v3",
            source_record_digest=DIGEST_A,
            normalized_digest=DIGEST_B,
            source_revision="gfs.20260812/18/f006",
            decoder_version="grib-field-decoder/0.2.0+eccodes/2.38.3",
            quality_disposition=QualityDisposition.ACCEPT,
            provenance=provenance,
        )

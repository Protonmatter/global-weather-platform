from weather_platform.acquisition.noaa.gfs import (
    GFS_COMPLETE_FIELDS,
    GFS_INDEX_REQUIREMENTS,
    GFS_MINIMUM_FIELDS,
    canonical_gfs_field_name,
)
from weather_platform.domain.model_catalog import ModelCycleField


def field(
    variable: str,
    level_type: str,
    level_value: float | None,
) -> ModelCycleField:
    return ModelCycleField(
        variable=variable,
        level_type=level_type,
        level_value=level_value,
        grid="regular_ll:1440x721",
        lead_hours=6,
    )


def test_minimum_manifest_contains_core_iqair_style_fields() -> None:
    assert (
        frozenset(
            {
                "u_wind_10m",
                "v_wind_10m",
                "air_temperature_2m",
                "relative_humidity_2m",
                "air_pressure_at_mean_sea_level",
            }
        )
        == GFS_MINIMUM_FIELDS
    )
    assert GFS_MINIMUM_FIELDS < GFS_COMPLETE_FIELDS


def test_index_requirements_have_unique_names() -> None:
    names = [requirement.name for requirement in GFS_INDEX_REQUIREMENTS]
    assert len(names) == len(set(names))
    assert set(names) == GFS_COMPLETE_FIELDS


def test_ec_codes_field_identity_maps_to_canonical_names() -> None:
    assert canonical_gfs_field_name(field("10u", "heightAboveGround", 10.0)) == "u_wind_10m"
    assert canonical_gfs_field_name(field("10v", "heightAboveGround", 10.0)) == "v_wind_10m"
    assert canonical_gfs_field_name(field("2t", "heightAboveGround", 2.0)) == "air_temperature_2m"
    assert canonical_gfs_field_name(field("2r", "heightAboveGround", 2.0)) == "relative_humidity_2m"
    assert canonical_gfs_field_name(field("prmsl", "meanSea", 0.0)) == (
        "air_pressure_at_mean_sea_level"
    )


def test_unknown_or_wrong_level_field_does_not_match() -> None:
    assert canonical_gfs_field_name(field("10u", "heightAboveGround", 80.0)) is None
    assert canonical_gfs_field_name(field("cape", "surface", 0.0)) is None

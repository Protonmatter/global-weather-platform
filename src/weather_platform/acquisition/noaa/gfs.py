import math

from weather_platform.acquisition.noaa.grib_index import FieldRequirement
from weather_platform.domain.model_catalog import ModelCycleField

GFS_INDEX_REQUIREMENTS: tuple[FieldRequirement, ...] = (
    FieldRequirement("u_wind_10m", ("UGRD", "10 m above ground")),
    FieldRequirement("v_wind_10m", ("VGRD", "10 m above ground")),
    FieldRequirement("air_temperature_2m", ("TMP", "2 m above ground")),
    FieldRequirement("relative_humidity_2m", ("RH", "2 m above ground")),
    FieldRequirement("air_pressure_at_mean_sea_level", ("PRMSL", "mean sea level")),
    FieldRequirement("wind_speed_of_gust", ("GUST", "surface")),
    FieldRequirement("cloud_area_fraction", ("TCDC", "entire atmosphere")),
    FieldRequirement("precipitation_amount", ("APCP", "surface")),
)

GFS_MINIMUM_FIELDS = frozenset(
    {
        "u_wind_10m",
        "v_wind_10m",
        "air_temperature_2m",
        "relative_humidity_2m",
        "air_pressure_at_mean_sea_level",
    }
)

GFS_COMPLETE_FIELDS = frozenset(requirement.name for requirement in GFS_INDEX_REQUIREMENTS)


def _normalized(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _level_matches(field: ModelCycleField, expected_type: str, expected_value: float) -> bool:
    if _normalized(field.level_type) != _normalized(expected_type):
        return False
    return field.level_value is not None and math.isclose(
        field.level_value,
        expected_value,
        rel_tol=0.0,
        abs_tol=1e-9,
    )


def canonical_gfs_field_name(field: ModelCycleField) -> str | None:
    """Map an ecCodes GFS field identity to the platform's canonical field name."""

    variable = field.variable.casefold()
    if variable == "10u" and _level_matches(field, "heightAboveGround", 10.0):
        return "u_wind_10m"
    if variable == "10v" and _level_matches(field, "heightAboveGround", 10.0):
        return "v_wind_10m"
    if variable == "2t" and _level_matches(field, "heightAboveGround", 2.0):
        return "air_temperature_2m"
    if variable == "2r" and _level_matches(field, "heightAboveGround", 2.0):
        return "relative_humidity_2m"
    if variable == "prmsl" and _level_matches(field, "meanSea", 0.0):
        return "air_pressure_at_mean_sea_level"
    if variable == "gust" and _level_matches(field, "surface", 0.0):
        return "wind_speed_of_gust"
    if variable == "tcc" and _normalized(field.level_type) in {
        _normalized("entireAtmosphere"),
        _normalized("atmosphere"),
    }:
        return "cloud_area_fraction"
    if variable == "tp" and _level_matches(field, "surface", 0.0):
        return "precipitation_amount"
    return None

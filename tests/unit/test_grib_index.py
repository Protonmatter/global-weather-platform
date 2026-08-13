import pytest

from weather_platform.acquisition.noaa.grib_index import (
    AmbiguousFieldError,
    FieldRequirement,
    GribIndexError,
    MissingRequiredFieldError,
    parse_grib_index,
    select_grib_messages,
)

INDEX = """1:0:d=2026081218:UGRD:10 m above ground:6 hour fcst:
2:120:d=2026081218:VGRD:10 m above ground:6 hour fcst:
3:240:d=2026081218:TMP:2 m above ground:6 hour fcst:
4:360:d=2026081218:PRMSL:mean sea level:6 hour fcst:
"""


def test_parse_derives_inclusive_ranges_including_final_message() -> None:
    entries = parse_grib_index(INDEX, object_size=500)
    assert [(entry.byte_start, entry.byte_end) for entry in entries] == [
        (0, 119),
        (120, 239),
        (240, 359),
        (360, 499),
    ]
    assert entries[0].descriptor_fields[:2] == ("d=2026081218", "UGRD")


def test_parse_accepts_crlf_and_missing_terminal_newline() -> None:
    entries = parse_grib_index(INDEX.replace("\n", "\r\n").rstrip(), object_size=500)
    assert len(entries) == 4


@pytest.mark.parametrize(
    "text",
    [
        "1:not-an-offset:d=2026081218:UGRD:10 m above ground:",
        "1:120:d=x:UGRD:\n2:100:d=x:VGRD:\n",
        "1:0:d=x:UGRD:\n2:0:d=x:VGRD:\n",
        "1:0",
        "",
    ],
)
def test_parse_rejects_malformed_or_non_monotonic_indexes(text: str) -> None:
    with pytest.raises(GribIndexError):
        parse_grib_index(text, object_size=500)


def test_parse_rejects_message_number_gaps_before_deriving_ranges() -> None:
    truncated = """1:0:d=x:UGRD:10 m above ground:
3:240:d=x:TMP:2 m above ground:
"""
    with pytest.raises(GribIndexError, match="consecutive"):
        parse_grib_index(truncated, object_size=500)


def test_parse_rejects_offset_outside_object() -> None:
    with pytest.raises(GribIndexError, match="object size"):
        parse_grib_index("1:500:d=x:UGRD:10 m above ground:\n", object_size=500)


def test_selection_requires_exactly_one_match_per_field() -> None:
    entries = parse_grib_index(INDEX, object_size=500)
    selected = select_grib_messages(
        entries,
        (
            FieldRequirement(name="u_wind_10m", tokens=("UGRD", "10 m above ground")),
            FieldRequirement(name="v_wind_10m", tokens=("VGRD", "10 m above ground")),
            FieldRequirement(name="air_temperature_2m", tokens=("TMP", "2 m above ground")),
        ),
    )
    assert [item.name for item in selected] == [
        "u_wind_10m",
        "v_wind_10m",
        "air_temperature_2m",
    ]
    assert selected[1].byte_start == 120
    assert selected[1].byte_end == 239


def test_selection_rejects_missing_required_field() -> None:
    entries = parse_grib_index(INDEX, object_size=500)
    with pytest.raises(MissingRequiredFieldError, match="relative_humidity_2m"):
        select_grib_messages(
            entries,
            (FieldRequirement(name="relative_humidity_2m", tokens=("RH", "2 m above ground")),),
        )


def test_selection_rejects_ambiguous_required_field() -> None:
    duplicated = INDEX + "5:480:d=2026081218:UGRD:10 m above ground:9 hour fcst:\n"
    entries = parse_grib_index(duplicated, object_size=600)
    with pytest.raises(AmbiguousFieldError, match="u_wind_10m"):
        select_grib_messages(
            entries,
            (FieldRequirement(name="u_wind_10m", tokens=("UGRD", "10 m above ground")),),
        )


def test_selection_is_case_insensitive_but_field_exact() -> None:
    entries = parse_grib_index(INDEX, object_size=500)
    selected = select_grib_messages(
        entries,
        (FieldRequirement(name="pressure", tokens=("prmsl", "MEAN SEA LEVEL")),),
    )
    assert selected[0].message_number == 4

import pytest

from weather_platform.acquisition.noaa.gfs import GFS_COMPLETE_FIELDS, GFS_MINIMUM_FIELDS
from weather_platform.domain.cycle_lifecycle import (
    CycleState,
    IllegalCycleTransition,
    evaluate_cycle,
    transition_cycle,
)


def test_empty_cycle_is_missing_and_not_usable() -> None:
    result = evaluate_cycle(
        set(),
        minimum_fields=GFS_MINIMUM_FIELDS,
        complete_fields=GFS_COMPLETE_FIELDS,
    )
    assert result.state is CycleState.MISSING
    assert not result.usable
    assert result.completeness_ratio == 0.0


def test_partial_cycle_is_visible_but_not_usable() -> None:
    result = evaluate_cycle(
        {"u_wind_10m", "v_wind_10m"},
        minimum_fields=GFS_MINIMUM_FIELDS,
        complete_fields=GFS_COMPLETE_FIELDS,
    )
    assert result.state is CycleState.PARTIAL
    assert not result.usable
    assert "air_temperature_2m" in result.missing_minimum_fields


def test_minimum_manifest_promotes_cycle_to_usable() -> None:
    result = evaluate_cycle(
        set(GFS_MINIMUM_FIELDS),
        minimum_fields=GFS_MINIMUM_FIELDS,
        complete_fields=GFS_COMPLETE_FIELDS,
    )
    assert result.state is CycleState.MINIMUM_USABLE
    assert result.usable
    assert result.missing_minimum_fields == frozenset()
    assert result.missing_complete_fields


def test_complete_cycle_is_distinct_from_minimum_usable() -> None:
    result = evaluate_cycle(
        set(GFS_COMPLETE_FIELDS),
        minimum_fields=GFS_MINIMUM_FIELDS,
        complete_fields=GFS_COMPLETE_FIELDS,
    )
    assert result.state is CycleState.COMPLETE
    assert result.usable
    assert result.completeness_ratio == 1.0


def test_duplicate_arrivals_do_not_inflate_completeness() -> None:
    result = evaluate_cycle(
        ["u_wind_10m", "u_wind_10m", "v_wind_10m"],
        minimum_fields=GFS_MINIMUM_FIELDS,
        complete_fields=GFS_COMPLETE_FIELDS,
    )
    assert result.available_fields == frozenset({"u_wind_10m", "v_wind_10m"})
    assert result.completeness_ratio == 2 / len(GFS_COMPLETE_FIELDS)


def test_illegal_backwards_transition_is_rejected() -> None:
    with pytest.raises(IllegalCycleTransition):
        transition_cycle(CycleState.COMPLETE, CycleState.PARTIAL)


def test_quarantine_and_forward_transitions_are_explicit() -> None:
    assert transition_cycle(CycleState.DISCOVERED, CycleState.INDEX_AVAILABLE) is (
        CycleState.INDEX_AVAILABLE
    )
    assert transition_cycle(CycleState.PARTIAL, CycleState.QUARANTINED) is CycleState.QUARANTINED
    assert transition_cycle(CycleState.COMPLETE, CycleState.SUPERSEDED) is CycleState.SUPERSEDED

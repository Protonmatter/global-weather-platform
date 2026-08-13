from collections.abc import Iterable

import pytest

from weather_platform.acquisition.noaa.gfs import GFS_COMPLETE_FIELDS, GFS_MINIMUM_FIELDS
from weather_platform.domain.cycle_lifecycle import (
    CycleFieldArrival,
    CycleProductScope,
    CycleState,
    IllegalCycleTransition,
    MismatchedCycleScopeError,
    evaluate_cycle,
    transition_cycle,
)

SCOPE = CycleProductScope(grid="gfs-0p25-global", lead_hours=6, member=None)


def arrivals(
    names: Iterable[str],
    *,
    scope: CycleProductScope = SCOPE,
) -> list[CycleFieldArrival]:
    return [CycleFieldArrival(name=name, scope=scope) for name in names]


def test_empty_cycle_is_missing_and_not_usable() -> None:
    result = evaluate_cycle(
        [],
        scope=SCOPE,
        minimum_fields=GFS_MINIMUM_FIELDS,
        complete_fields=GFS_COMPLETE_FIELDS,
    )
    assert result.scope == SCOPE
    assert result.state is CycleState.MISSING
    assert not result.usable
    assert result.completeness_ratio == 0.0


def test_partial_cycle_is_visible_but_not_usable() -> None:
    result = evaluate_cycle(
        arrivals({"u_wind_10m", "v_wind_10m"}),
        scope=SCOPE,
        minimum_fields=GFS_MINIMUM_FIELDS,
        complete_fields=GFS_COMPLETE_FIELDS,
    )
    assert result.state is CycleState.PARTIAL
    assert not result.usable
    assert "air_temperature_2m" in result.missing_minimum_fields


def test_minimum_manifest_promotes_cycle_to_usable() -> None:
    result = evaluate_cycle(
        arrivals(GFS_MINIMUM_FIELDS),
        scope=SCOPE,
        minimum_fields=GFS_MINIMUM_FIELDS,
        complete_fields=GFS_COMPLETE_FIELDS,
    )
    assert result.state is CycleState.MINIMUM_USABLE
    assert result.usable
    assert result.missing_minimum_fields == frozenset()
    assert result.missing_complete_fields


def test_complete_cycle_is_distinct_from_minimum_usable() -> None:
    result = evaluate_cycle(
        arrivals(GFS_COMPLETE_FIELDS),
        scope=SCOPE,
        minimum_fields=GFS_MINIMUM_FIELDS,
        complete_fields=GFS_COMPLETE_FIELDS,
    )
    assert result.state is CycleState.COMPLETE
    assert result.usable
    assert result.completeness_ratio == 1.0


def test_duplicate_arrivals_do_not_inflate_completeness() -> None:
    result = evaluate_cycle(
        arrivals(["u_wind_10m", "u_wind_10m", "v_wind_10m"]),
        scope=SCOPE,
        minimum_fields=GFS_MINIMUM_FIELDS,
        complete_fields=GFS_COMPLETE_FIELDS,
    )
    assert result.available_fields == frozenset({"u_wind_10m", "v_wind_10m"})
    assert result.completeness_ratio == 2 / len(GFS_COMPLETE_FIELDS)


def test_arrivals_from_different_leads_cannot_form_one_usable_product() -> None:
    later_scope = CycleProductScope(grid=SCOPE.grid, lead_hours=9, member=None)
    mixed = [
        CycleFieldArrival(name="u_wind_10m", scope=SCOPE),
        CycleFieldArrival(name="v_wind_10m", scope=later_scope),
        CycleFieldArrival(name="air_temperature_2m", scope=later_scope),
        CycleFieldArrival(name="relative_humidity_2m", scope=later_scope),
        CycleFieldArrival(name="air_pressure_at_mean_sea_level", scope=later_scope),
    ]
    with pytest.raises(MismatchedCycleScopeError, match="scope"):
        evaluate_cycle(
            mixed,
            scope=SCOPE,
            minimum_fields=GFS_MINIMUM_FIELDS,
            complete_fields=GFS_COMPLETE_FIELDS,
        )


def test_scope_rejects_empty_grid_negative_lead_and_empty_member() -> None:
    with pytest.raises(ValueError, match="grid"):
        CycleProductScope(grid="", lead_hours=6, member=None)
    with pytest.raises(ValueError, match="lead_hours"):
        CycleProductScope(grid="gfs-0p25-global", lead_hours=-1, member=None)
    with pytest.raises(ValueError, match="member"):
        CycleProductScope(grid="gfs-0p25-global", lead_hours=6, member="")


def test_illegal_backwards_transition_is_rejected() -> None:
    with pytest.raises(IllegalCycleTransition):
        transition_cycle(CycleState.COMPLETE, CycleState.PARTIAL)


def test_complete_cycle_can_be_quarantined_before_publication() -> None:
    assert transition_cycle(CycleState.COMPLETE, CycleState.QUARANTINED) is CycleState.QUARANTINED


def test_quarantine_and_forward_transitions_are_explicit() -> None:
    assert transition_cycle(CycleState.DISCOVERED, CycleState.INDEX_AVAILABLE) is (
        CycleState.INDEX_AVAILABLE
    )
    assert transition_cycle(CycleState.PARTIAL, CycleState.QUARANTINED) is CycleState.QUARANTINED
    assert transition_cycle(CycleState.COMPLETE, CycleState.SUPERSEDED) is CycleState.SUPERSEDED

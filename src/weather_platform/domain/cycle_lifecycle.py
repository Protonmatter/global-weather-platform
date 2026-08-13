from collections.abc import Iterable, Set
from dataclasses import dataclass
from enum import StrEnum


class CycleState(StrEnum):
    DISCOVERED = "discovered"
    INDEX_AVAILABLE = "index_available"
    DOWNLOADING = "downloading"
    MISSING = "missing"
    PARTIAL = "partial"
    MINIMUM_USABLE = "minimum_usable"
    COMPLETE = "complete"
    QUARANTINED = "quarantined"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class IllegalCycleTransition(ValueError):
    """Raised when a model cycle attempts an invalid lifecycle transition."""


class MismatchedCycleScopeError(ValueError):
    """Raised when fields from different products are evaluated together."""


@dataclass(frozen=True, slots=True)
class CycleProductScope:
    """Dimensions that define one coherent model product inventory."""

    grid: str
    lead_hours: int
    member: str | None = None

    def __post_init__(self) -> None:
        if not self.grid.strip():
            raise ValueError("grid must not be empty")
        if self.lead_hours < 0:
            raise ValueError("lead_hours must be non-negative")
        if self.member is not None and not self.member.strip():
            raise ValueError("member must not be empty")


@dataclass(frozen=True, slots=True)
class CycleFieldArrival:
    """A canonical field arrival bound to its complete product scope."""

    name: str
    scope: CycleProductScope

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("field name must not be empty")


@dataclass(frozen=True, slots=True)
class CyclePublicationState:
    scope: CycleProductScope
    state: CycleState
    available_fields: frozenset[str]
    missing_minimum_fields: frozenset[str]
    missing_complete_fields: frozenset[str]
    completeness_ratio: float

    @property
    def usable(self) -> bool:
        return self.state in {CycleState.MINIMUM_USABLE, CycleState.COMPLETE}


def evaluate_cycle(
    available_fields: Iterable[CycleFieldArrival],
    *,
    scope: CycleProductScope,
    minimum_fields: Set[str],
    complete_fields: Set[str],
) -> CyclePublicationState:
    """Evaluate one grid, lead, and ensemble-member product for publication."""

    minimum = frozenset(minimum_fields)
    complete = frozenset(complete_fields)
    if not minimum:
        raise ValueError("minimum_fields must not be empty")
    if not complete:
        raise ValueError("complete_fields must not be empty")
    if not minimum <= complete:
        raise ValueError("minimum_fields must be a subset of complete_fields")

    arrivals = tuple(available_fields)
    mismatched = [arrival for arrival in arrivals if arrival.scope != scope]
    if mismatched:
        raise MismatchedCycleScopeError(
            "all available fields must match the evaluated grid, lead, and member scope"
        )

    available = frozenset(arrival.name for arrival in arrivals)
    recognized = available & complete
    missing_minimum = minimum - recognized
    missing_complete = complete - recognized
    ratio = len(recognized) / len(complete)

    if not recognized:
        state = CycleState.MISSING
    elif not missing_complete:
        state = CycleState.COMPLETE
    elif not missing_minimum:
        state = CycleState.MINIMUM_USABLE
    else:
        state = CycleState.PARTIAL

    return CyclePublicationState(
        scope=scope,
        state=state,
        available_fields=available,
        missing_minimum_fields=frozenset(missing_minimum),
        missing_complete_fields=frozenset(missing_complete),
        completeness_ratio=ratio,
    )


_ALLOWED_TRANSITIONS: dict[CycleState, frozenset[CycleState]] = {
    CycleState.DISCOVERED: frozenset(
        {CycleState.INDEX_AVAILABLE, CycleState.MISSING, CycleState.QUARANTINED}
    ),
    CycleState.INDEX_AVAILABLE: frozenset(
        {CycleState.DOWNLOADING, CycleState.PARTIAL, CycleState.QUARANTINED}
    ),
    CycleState.DOWNLOADING: frozenset(
        {
            CycleState.MISSING,
            CycleState.PARTIAL,
            CycleState.MINIMUM_USABLE,
            CycleState.COMPLETE,
            CycleState.QUARANTINED,
        }
    ),
    CycleState.MISSING: frozenset({CycleState.PARTIAL, CycleState.QUARANTINED, CycleState.EXPIRED}),
    CycleState.PARTIAL: frozenset(
        {
            CycleState.MINIMUM_USABLE,
            CycleState.COMPLETE,
            CycleState.QUARANTINED,
            CycleState.EXPIRED,
        }
    ),
    CycleState.MINIMUM_USABLE: frozenset(
        {
            CycleState.COMPLETE,
            CycleState.QUARANTINED,
            CycleState.SUPERSEDED,
            CycleState.EXPIRED,
        }
    ),
    CycleState.COMPLETE: frozenset(
        {CycleState.QUARANTINED, CycleState.SUPERSEDED, CycleState.EXPIRED}
    ),
    CycleState.QUARANTINED: frozenset({CycleState.EXPIRED}),
    CycleState.SUPERSEDED: frozenset({CycleState.EXPIRED}),
    CycleState.EXPIRED: frozenset(),
}


def transition_cycle(current: CycleState, target: CycleState) -> CycleState:
    """Apply an explicit, monotonic model-cycle lifecycle transition."""

    if current == target:
        return target
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise IllegalCycleTransition(f"illegal model-cycle transition {current} -> {target}")
    return target

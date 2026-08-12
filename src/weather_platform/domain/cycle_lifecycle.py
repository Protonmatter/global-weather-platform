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


@dataclass(frozen=True, slots=True)
class CyclePublicationState:
    state: CycleState
    available_fields: frozenset[str]
    missing_minimum_fields: frozenset[str]
    missing_complete_fields: frozenset[str]
    completeness_ratio: float

    @property
    def usable(self) -> bool:
        return self.state in {CycleState.MINIMUM_USABLE, CycleState.COMPLETE}


def evaluate_cycle(
    available_fields: Iterable[str],
    *,
    minimum_fields: Set[str],
    complete_fields: Set[str],
) -> CyclePublicationState:
    """Evaluate publication eligibility from unique canonical field identities."""

    minimum = frozenset(minimum_fields)
    complete = frozenset(complete_fields)
    if not minimum:
        raise ValueError("minimum_fields must not be empty")
    if not complete:
        raise ValueError("complete_fields must not be empty")
    if not minimum <= complete:
        raise ValueError("minimum_fields must be a subset of complete_fields")

    available = frozenset(available_fields)
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
    CycleState.COMPLETE: frozenset({CycleState.SUPERSEDED, CycleState.EXPIRED}),
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

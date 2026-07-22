import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from weather_platform.domain.models import Observation


@dataclass(frozen=True)
class AvailabilitySplit:
    """Observations partitioned by whether they were usable at issue time."""

    available: list[Observation]
    corrected: list[Observation]


def partition_by_availability(
    observations: Sequence[Observation], issued_at: AwareDatetime
) -> AvailabilitySplit:
    """Split observations into those operationally available at issue time and later corrections.

    Availability uses ``ingestion_time`` — the moment a record entered the
    canonical store and became usable. Records that entered after the simulated
    issue time are corrections or backfill and must never inform a forecast
    evaluated at that issue time (VAL-LEAK-0003).
    """
    available: list[Observation] = []
    corrected: list[Observation] = []
    for observation in observations:
        if observation.ingestion_time <= issued_at:
            available.append(observation)
        else:
            corrected.append(observation)
    return AvailabilitySplit(available=available, corrected=corrected)


class Baseline(ABC):
    """A deterministic, versioned reference forecast method."""

    id: str
    version: str

    @abstractmethod
    def forecast(self, available: Sequence[Observation], phenomenon: str) -> float | None:
        """Return a point forecast from operationally available observations only."""


class PersistenceBaseline(Baseline):
    id = "persistence"
    version = "persistence/1"

    def forecast(self, available: Sequence[Observation], phenomenon: str) -> float | None:
        candidates = [o for o in available if o.phenomenon == phenomenon and o.value is not None]
        if not candidates:
            return None
        # Ties on observation_time break on the latest ingestion for determinism.
        latest = max(candidates, key=lambda o: (o.observation_time, o.ingestion_time))
        return latest.value


class ClimatologyBaseline(Baseline):
    id = "climatology"
    version = "climatology/1"

    def forecast(self, available: Sequence[Observation], phenomenon: str) -> float | None:
        values = [o.value for o in available if o.phenomenon == phenomenon and o.value is not None]
        if not values:
            return None
        return math.fsum(values) / len(values)


class VerificationCase(BaseModel):
    """One ledger entry pairing a baseline forecast with the verifying observation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0.0"
    baseline_id: str = Field(min_length=1)
    baseline_version: str = Field(min_length=1)
    phenomenon: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    issued_at: AwareDatetime
    valid_time: AwareDatetime
    forecast_value: float | None
    observed_value: float | None
    verifying_observation_id: UUID
    operationally_available_count: int = Field(ge=0)
    corrected_excluded_count: int = Field(ge=0)


def build_verification_case(
    *,
    baseline: Baseline,
    phenomenon: str,
    issued_at: AwareDatetime,
    valid_time: AwareDatetime,
    observations: Sequence[Observation],
    verifying_observation: Observation,
) -> VerificationCase:
    """Assemble a leakage-safe verification case.

    The baseline forecast is computed only from observations operationally
    available at ``issued_at``; the case records how many were available versus
    excluded as corrections, so availability-at-issue is auditable.
    """
    if valid_time <= issued_at:
        raise ValueError("valid_time must be after issued_at")
    split = partition_by_availability(observations, issued_at)
    forecast_value = baseline.forecast(split.available, phenomenon)
    return VerificationCase(
        baseline_id=baseline.id,
        baseline_version=baseline.version,
        phenomenon=phenomenon,
        issued_at=issued_at,
        valid_time=valid_time,
        forecast_value=forecast_value,
        observed_value=verifying_observation.value,
        verifying_observation_id=verifying_observation.observation_id,
        operationally_available_count=len(split.available),
        corrected_excluded_count=len(split.corrected),
    )

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from weather_platform.domain.models import Observation
from weather_platform.scientific.verification import (
    ClimatologyBaseline,
    PersistenceBaseline,
    build_verification_case,
    partition_by_availability,
)
from weather_platform.storage.verification_ledger import VerificationLedger

ROOT = Path(__file__).resolve().parents[2]
ISSUE = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
VALID = datetime(2026, 7, 20, 18, 0, tzinfo=UTC)


def obs(value: float, observed: str, ingested: str, obs_id: UUID | None = None) -> Observation:
    record = json.loads((ROOT / "testdata/observations/temperature.json").read_text())
    record["observation_id"] = str(obs_id or uuid4())
    record["value"] = value
    record["observation_time"] = observed
    record["ingestion_time"] = ingested
    return Observation.model_validate(record)


# Available at issue time; a late correction that arrived after issue time.
AVAILABLE = obs(300.0, "2026-07-20T11:00:00Z", "2026-07-20T11:05:00Z")
LATE_CORRECTION = obs(999.0, "2026-07-20T11:30:00Z", "2026-07-20T18:00:00Z")
TRUTH = obs(305.0, "2026-07-20T18:00:00Z", "2026-07-20T18:02:00Z")


def test_partition_separates_operational_from_corrected() -> None:
    split = partition_by_availability([AVAILABLE, LATE_CORRECTION], ISSUE)
    assert split.available == [AVAILABLE]
    assert split.corrected == [LATE_CORRECTION]


def test_baseline_never_uses_data_unavailable_at_issue() -> None:
    case = build_verification_case(
        baseline=PersistenceBaseline(),
        phenomenon="air_temperature",
        issued_at=ISSUE,
        valid_time=VALID,
        observations=[AVAILABLE, LATE_CORRECTION],
        verifying_observation=TRUTH,
    )
    # The later, larger correction must not leak into the forecast.
    assert case.forecast_value == 300.0
    assert case.operationally_available_count == 1
    assert case.corrected_excluded_count == 1
    assert case.observed_value == 305.0
    assert case.verifying_observation_id == TRUTH.observation_id


def test_case_records_baseline_version_and_is_reproducible() -> None:
    kwargs = dict(
        phenomenon="air_temperature",
        issued_at=ISSUE,
        valid_time=VALID,
        observations=[AVAILABLE, LATE_CORRECTION],
        verifying_observation=TRUTH,
    )
    first = build_verification_case(baseline=PersistenceBaseline(), **kwargs)
    second = build_verification_case(baseline=PersistenceBaseline(), **kwargs)
    assert first == second
    assert first.baseline_version == "persistence/1"

    early = obs(310.0, "2026-07-20T10:00:00Z", "2026-07-20T10:05:00Z")
    climatology = build_verification_case(
        baseline=ClimatologyBaseline(),
        phenomenon="air_temperature",
        issued_at=ISSUE,
        valid_time=VALID,
        observations=[AVAILABLE, early, LATE_CORRECTION],
        verifying_observation=TRUTH,
    )
    assert climatology.baseline_version == "climatology/1"
    assert climatology.forecast_value == 305.0  # mean(300, 310); late correction excluded


def test_valid_time_must_be_after_issue() -> None:
    with pytest.raises(ValueError, match="valid_time must be after"):
        build_verification_case(
            baseline=PersistenceBaseline(),
            phenomenon="air_temperature",
            issued_at=ISSUE,
            valid_time=ISSUE,
            observations=[AVAILABLE],
            verifying_observation=TRUTH,
        )


def test_ledger_round_trip(tmp_path: Path) -> None:
    ledger = VerificationLedger(tmp_path / "verification.jsonl")
    case = build_verification_case(
        baseline=PersistenceBaseline(),
        phenomenon="air_temperature",
        issued_at=ISSUE,
        valid_time=VALID,
        observations=[AVAILABLE],
        verifying_observation=TRUTH,
    )
    ledger.record(case)
    assert ledger.list(baseline_id="persistence") == [case]
    assert ledger.list(baseline_id="climatology") == []

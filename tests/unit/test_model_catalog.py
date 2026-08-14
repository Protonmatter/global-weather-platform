from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from weather_platform.domain.model_catalog import (
    CycleCompleteness,
    GuidanceOrigin,
    ModelCycleField,
    ModelGuidanceCycle,
)
from weather_platform.provenance import sha256_digest
from weather_platform.storage.model_catalog_store import ModelGuidanceCatalog

INIT = datetime(2026, 7, 22, 0, 0, tzinfo=UTC)


def field(variable: str = "temperature", lead_hours: int = 0) -> ModelCycleField:
    return ModelCycleField(
        variable=variable,
        level_type="isobaric",
        level_value=850.0,
        grid="0p25",
        lead_hours=lead_hours,
    )


def cycle(available: list[ModelCycleField], **overrides: object) -> ModelGuidanceCycle:
    base = {
        "model_id": "gfs",
        "model_version": "v16.3",
        "guidance_origin": GuidanceOrigin.IMPORTED,
        "initialized_at": INIT,
        "source_revision": "2026072200",
        "grids": ["0p25"],
        "expected_fields": [field(lead_hours=0), field(lead_hours=6), field(lead_hours=12)],
        "available_fields": available,
    }
    base.update(overrides)
    return ModelGuidanceCycle.model_validate(base)


def test_completeness_reflects_available_versus_expected() -> None:
    expected = [field(lead_hours=0), field(lead_hours=6), field(lead_hours=12)]
    assert cycle(expected).completeness() is CycleCompleteness.COMPLETE
    assert cycle(expected[:2]).completeness() is CycleCompleteness.PARTIAL
    assert cycle([]).completeness() is CycleCompleteness.MISSING


def test_missing_fields_are_explicit() -> None:
    partial = cycle([field(lead_hours=0)])
    missing = {f.lead_hours for f in partial.missing_fields()}
    assert missing == {6, 12}


def test_inventory_validation_rejects_inconsistent_cycles() -> None:
    with pytest.raises(ValidationError):  # available not a subset of expected
        cycle([field(variable="wind_speed")])
    with pytest.raises(ValidationError):  # duplicate expected fields
        cycle([], expected_fields=[field(lead_hours=0), field(lead_hours=0)])


def test_guidance_origin_is_required() -> None:
    with pytest.raises(ValidationError):
        cycle([], guidance_origin=None)


def test_catalog_latest_entry_wins_per_cycle_key(tmp_path: Path) -> None:
    catalog = ModelGuidanceCatalog(tmp_path / "model-cycles.jsonl")
    catalog.register(cycle([field(lead_hours=0)]))  # partial
    catalog.register(cycle([field(lead_hours=0), field(lead_hours=6), field(lead_hours=12)]))
    listed = catalog.list(model_id="gfs")
    assert len(listed) == 1
    assert listed[0].completeness() is CycleCompleteness.COMPLETE


def test_catalog_filters_by_origin(tmp_path: Path) -> None:
    catalog = ModelGuidanceCatalog(tmp_path / "model-cycles.jsonl")
    catalog.register(cycle([field()], guidance_origin=GuidanceOrigin.IMPORTED))
    catalog.register(
        cycle([field()], model_id="platform-blend", guidance_origin=GuidanceOrigin.PLATFORM)
    )
    imported = catalog.list(guidance_origin=GuidanceOrigin.IMPORTED)
    assert [c.model_id for c in imported] == ["gfs"]


def test_catalog_binds_an_append_to_its_mutation_identity(tmp_path: Path) -> None:
    catalog = ModelGuidanceCatalog(tmp_path / "model-cycles.jsonl")
    item = cycle([field()])
    mutation_id = uuid4()

    catalog.register(item, mutation_id=mutation_id)

    assert catalog.contains_mutation(
        mutation_id,
        sha256_digest(item.model_dump_json().encode("utf-8")),
    )
    assert not catalog.contains_mutation(
        uuid4(),
        sha256_digest(item.model_dump_json().encode("utf-8")),
    )

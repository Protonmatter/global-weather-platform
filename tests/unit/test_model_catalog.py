import os
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


def test_catalog_repairs_only_a_torn_final_record_before_recovery(tmp_path: Path) -> None:
    path = tmp_path / "model-cycles.jsonl"
    catalog = ModelGuidanceCatalog(path)
    retained = cycle([field(lead_hours=0)])
    catalog.register(retained)
    with path.open("ab") as handle:
        handle.write(b'{"mutation_id":"torn')
        handle.flush()
        os.fsync(handle.fileno())

    restarted = ModelGuidanceCatalog(path)

    assert restarted.list() == [retained]
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_catalog_rejects_a_malformed_newline_terminated_record(tmp_path: Path) -> None:
    path = tmp_path / "model-cycles.jsonl"
    catalog = ModelGuidanceCatalog(path)
    catalog.register(cycle([field(lead_hours=0)]))
    with path.open("ab") as handle:
        handle.write(b"not-json\n")
        handle.flush()
        os.fsync(handle.fileno())

    restarted = ModelGuidanceCatalog(path)

    with pytest.raises(ValueError, match="invalid model cycle at line 2"):
        restarted.list()


def test_catalog_repairs_a_crashed_writer_before_a_later_instance_appends(tmp_path: Path) -> None:
    path = tmp_path / "model-cycles.jsonl"
    first = ModelGuidanceCatalog(path)
    later = ModelGuidanceCatalog(path)
    retained = cycle([field(lead_hours=0)])
    appended = cycle([field(lead_hours=6)], source_revision="2026072206")
    first.register(retained)
    with path.open("ab") as handle:
        handle.write(b'{"mutation_id":"torn')
        handle.flush()
        os.fsync(handle.fileno())

    later.register(appended)

    assert later.list() == [retained, appended]


def test_catalog_repairs_a_torn_tail_before_an_existing_instance_reads(
    tmp_path: Path,
) -> None:
    path = tmp_path / "model-cycles.jsonl"
    catalog = ModelGuidanceCatalog(path)
    retained = cycle([field(lead_hours=0)])
    mutation_id = uuid4()
    catalog.register(retained, mutation_id=mutation_id)
    with path.open("ab") as handle:
        handle.write(b'{"mutation_id":"torn')
        handle.flush()
        os.fsync(handle.fileno())

    assert catalog.contains_mutation(
        mutation_id,
        sha256_digest(retained.model_dump_json().encode("utf-8")),
    )
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_catalog_rolls_back_a_partial_append_failure(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "model-cycles.jsonl"
    catalog = ModelGuidanceCatalog(path)
    retained = cycle([field(lead_hours=0)])
    rejected = cycle([field(lead_hours=6)], source_revision="2026072206")
    catalog.register(retained)
    original = path.read_bytes()
    write = os.write
    interrupted = False

    def interrupt_once(descriptor: int, payload: bytes) -> int:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            write(descriptor, payload[: max(1, len(payload) // 2)])
            raise OSError("simulated partial catalog write")
        return write(descriptor, payload)

    monkeypatch.setattr(os, "write", interrupt_once)

    with pytest.raises(OSError, match="partial catalog write"):
        catalog.register(rejected)

    assert path.read_bytes() == original
    assert catalog.list() == [retained]

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from weather_platform.domain.models import Observation
from weather_platform.provenance import sha256_digest
from weather_platform.storage.jsonl import JsonlObservationStore

ROOT = Path(__file__).resolve().parents[2]


def load_observation() -> Observation:
    record = json.loads((ROOT / "testdata/observations/temperature.json").read_text())
    return Observation.model_validate(record)


def test_append_and_filter(tmp_path: Path) -> None:
    record = json.loads((ROOT / "testdata/observations/temperature.json").read_text())
    observation = Observation.model_validate(record)
    store = JsonlObservationStore(tmp_path / "observations.jsonl")
    store.append(observation)
    assert store.list(phenomenon="air_temperature") == [observation]
    assert store.list(phenomenon="wind_speed") == []


def test_store_limit_and_compaction(tmp_path: Path) -> None:
    record = json.loads((ROOT / "testdata/observations/temperature.json").read_text())
    observation = Observation.model_validate(record)
    path = tmp_path / "observations.jsonl"
    store = JsonlObservationStore(path)
    store.append(observation)
    store.compact_atomically()
    assert store.list(limit=1) == [observation]
    import pytest

    with pytest.raises(ValueError, match="limit"):
        store.list(limit=0)


def test_store_reports_corrupt_line(tmp_path: Path) -> None:
    import pytest

    path = tmp_path / "observations.jsonl"
    path.write_text("not-json\n", encoding="utf-8")
    store = JsonlObservationStore(path)
    with pytest.raises(ValueError, match="line 1"):
        list(store.iter_observations())


def test_empty_store(tmp_path: Path) -> None:
    store = JsonlObservationStore(tmp_path / "missing.jsonl")
    assert store.list() == []


def test_transaction_is_reentrant(tmp_path: Path) -> None:
    store = JsonlObservationStore(tmp_path / "observations.jsonl")
    observation = load_observation()
    # append() takes the transaction internally; nesting it must not deadlock.
    with store.transaction():
        store.append(observation)
        with store.transaction():
            store.append(observation)
    assert len(store.list(include_quarantined=True)) == 2


def test_concurrent_appends_do_not_corrupt_the_store(tmp_path: Path) -> None:
    store = JsonlObservationStore(tmp_path / "observations.jsonl")
    observation = load_observation()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: store.append(observation), range(40)))
    # Every line parses: no interleaved or torn writes under the lock.
    assert len(store.list(include_quarantined=True)) == 40


def test_ingestion_marker_verifies_the_original_canonical_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "observations.jsonl"
    store = JsonlObservationStore(path)
    observation = load_observation()
    mutation_id = uuid4()
    source_digest = observation.provenance.source_record_digest
    if not hasattr(os, "O_DIRECTORY"):
        monkeypatch.setattr(store, "_fsync_directory", lambda _path: None)
    store.append(observation)

    store.record_ingestion_mutation(
        mutation_id,
        source_digest=source_digest,
        observations=[observation],
    )

    restarted = JsonlObservationStore(path)
    assert restarted.contains_ingestion_mutation(mutation_id, source_digest)
    assert not restarted.contains_ingestion_mutation(uuid4(), source_digest)
    assert not restarted.contains_ingestion_mutation(
        mutation_id,
        sha256_digest(b"different source"),
    )


def test_ingestion_marker_redelivery_is_idempotent_and_conflicts_fail_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import pytest

    store = JsonlObservationStore(tmp_path / "observations.jsonl")
    observation = load_observation()
    mutation_id = uuid4()
    source_digest = observation.provenance.source_record_digest
    if not hasattr(os, "O_DIRECTORY"):
        monkeypatch.setattr(store, "_fsync_directory", lambda _path: None)

    store.record_ingestion_mutation(
        mutation_id,
        source_digest=source_digest,
        observations=[observation],
    )
    store.record_ingestion_mutation(
        mutation_id,
        source_digest=source_digest,
        observations=[observation],
    )

    with pytest.raises(ValueError, match="conflicting ingestion marker"):
        store.record_ingestion_mutation(
            mutation_id,
            source_digest=sha256_digest(b"different source"),
            observations=[observation],
        )


def test_ingestion_marker_rejects_malformed_existing_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import pytest

    store = JsonlObservationStore(tmp_path / "observations.jsonl")
    observation = load_observation()
    mutation_id = uuid4()
    source_digest = observation.provenance.source_record_digest
    if not hasattr(os, "O_DIRECTORY"):
        monkeypatch.setattr(store, "_fsync_directory", lambda _path: None)
    marker = store._ingestion_marker(mutation_id)
    marker.write_text("not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid ingestion marker"):
        store.record_ingestion_mutation(
            mutation_id,
            source_digest=source_digest,
            observations=[observation],
        )

    marker.write_text(
        json.dumps(
            {
                "mutation_id": str(mutation_id),
                "source_record_digest": source_digest,
                "observations": [{"observation_id": str(observation.observation_id)}],
            }
        ),
        encoding="utf-8",
    )
    assert not store.contains_ingestion_mutation(mutation_id, source_digest)

    marker.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid ingestion marker"):
        store.contains_ingestion_mutation(mutation_id, source_digest)


def test_ingestion_marker_publish_failure_removes_the_temporary_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import pytest

    store = JsonlObservationStore(tmp_path / "observations.jsonl")
    observation = load_observation()
    mutation_id = uuid4()
    if not hasattr(os, "O_DIRECTORY"):
        monkeypatch.setattr(store, "_fsync_directory", lambda _path: None)

    def fail_replace(_source, _destination) -> None:
        raise OSError("simulated marker publish failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="marker publish failure"):
        store.record_ingestion_mutation(
            mutation_id,
            source_digest=observation.provenance.source_record_digest,
            observations=[observation],
        )

    assert list(store._ingestion_path.iterdir()) == []


def test_observation_replay_ignores_blank_lines(tmp_path: Path) -> None:
    observation = load_observation()
    path = tmp_path / "observations.jsonl"
    path.write_text(f"\n{observation.model_dump_json()}\n", encoding="utf-8")

    assert list(JsonlObservationStore(path).iter_observations()) == [observation]

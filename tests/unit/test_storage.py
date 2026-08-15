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
    with pytest.raises(ValueError, match="invalid ingestion marker"):
        store.contains_ingestion_mutation(mutation_id, source_digest)

    marker.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid ingestion marker"):
        store.contains_ingestion_mutation(mutation_id, source_digest)


def test_interrupted_ingestion_batch_never_exposes_a_receipt_before_observations(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import pytest

    store = JsonlObservationStore(tmp_path / "observations.jsonl")
    observation = load_observation()
    mutation_id = uuid4()
    redelivery_id = uuid4()
    source_digest = observation.provenance.source_record_digest

    def interrupt_after_observations(descriptor: int, payload: bytes) -> None:
        observation_end = payload.index(b"\n") + 1
        os.write(descriptor, payload[:observation_end])
        raise KeyboardInterrupt

    monkeypatch.setattr(store, "_write_all", interrupt_after_observations)
    with pytest.raises(KeyboardInterrupt):
        store.commit_ingestion_batch(
            mutation_id,
            source_digest=source_digest,
            appended_observations=[observation],
            canonical_observations=[observation],
        )

    restarted = JsonlObservationStore(store.path)
    assert list(restarted.iter_observations()) == [observation]
    assert not restarted.contains_ingestion_mutation(mutation_id, source_digest)

    restarted.commit_ingestion_batch(
        redelivery_id,
        source_digest=source_digest,
        appended_observations=[],
        canonical_observations=[observation],
    )
    assert restarted.contains_ingestion_mutation(redelivery_id, source_digest)
    assert not restarted.contains_ingestion_mutation(mutation_id, source_digest)


def test_compaction_preserves_embedded_ingestion_receipts(tmp_path: Path) -> None:
    store = JsonlObservationStore(tmp_path / "observations.jsonl")
    observation = load_observation()
    mutation_id = uuid4()
    source_digest = observation.provenance.source_record_digest
    store.commit_ingestion_batch(
        mutation_id,
        source_digest=source_digest,
        appended_observations=[observation],
        canonical_observations=[observation],
    )

    store.compact_atomically()

    assert list(store.iter_observations()) == [observation]
    assert store.contains_ingestion_mutation(mutation_id, source_digest)


def test_restart_repairs_only_an_incomplete_observation_tail(tmp_path: Path) -> None:
    store = JsonlObservationStore(tmp_path / "observations.jsonl")
    first = load_observation()
    second = first.model_copy(update={"observation_id": uuid4()})
    store.append(first)
    with store.path.open("ab") as handle:
        encoded = second.model_dump_json().encode("utf-8")
        handle.write(encoded[: len(encoded) // 2])
        handle.flush()
        os.fsync(handle.fileno())

    restarted = JsonlObservationStore(store.path)
    assert list(restarted.iter_observations()) == [first]
    restarted.append(second)
    assert list(restarted.iter_observations()) == [first, second]


def test_restart_preserves_a_complete_observation_missing_its_newline(tmp_path: Path) -> None:
    observation = load_observation()
    path = tmp_path / "observations.jsonl"
    path.write_bytes(observation.model_dump_json().encode("utf-8"))

    assert list(JsonlObservationStore(path).iter_observations()) == [observation]
    assert path.read_bytes().endswith(b"\n")


def test_ingestion_receipt_validation_fails_closed(tmp_path: Path, monkeypatch) -> None:
    import pytest

    store = JsonlObservationStore(tmp_path / "observations.jsonl")
    invalid_receipts = [
        {"record_type": "ingestion_mutation"},
        {
            "record_type": "ingestion_mutation",
            "mutation_id": 1,
            "source_record_digest": "sha256:" + "a" * 64,
            "observations": [],
        },
        {
            "record_type": "ingestion_mutation",
            "mutation_id": str(uuid4()),
            "source_record_digest": "sha256:" + "a" * 64,
            "observations": [{}],
        },
    ]
    for receipt in invalid_receipts:
        with pytest.raises(ValueError, match="invalid ingestion receipt"):
            store._parse_ingestion_payload(receipt, "test")

    monkeypatch.setattr(os, "write", lambda _descriptor, _payload: 0)
    with pytest.raises(OSError, match="no progress"):
        store._write_all(1, b"receipt")


def test_valid_legacy_ingestion_marker_remains_readable(tmp_path: Path) -> None:
    store = JsonlObservationStore(tmp_path / "observations.jsonl")
    observation = load_observation()
    mutation_id = uuid4()
    source_digest = observation.provenance.source_record_digest
    store.append(observation)
    legacy = store._ingestion_payload(mutation_id, source_digest, [observation])
    legacy.pop("record_type")
    store._ingestion_marker(mutation_id).write_text(json.dumps(legacy), encoding="utf-8")

    store.record_ingestion_mutation(
        mutation_id,
        source_digest=source_digest,
        observations=[observation],
    )

    assert store.contains_ingestion_mutation(mutation_id, source_digest)


def test_observation_replay_ignores_blank_lines(tmp_path: Path) -> None:
    observation = load_observation()
    path = tmp_path / "observations.jsonl"
    path.write_text(f"\n{observation.model_dump_json()}\n", encoding="utf-8")

    assert list(JsonlObservationStore(path).iter_observations()) == [observation]

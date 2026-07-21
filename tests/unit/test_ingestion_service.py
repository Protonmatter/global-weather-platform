from datetime import UTC, datetime
from pathlib import Path

import pytest

from weather_platform.ingestion.adapters.json_observation import JsonObservationAdapter
from weather_platform.ingestion.base import ObservationAdapter
from weather_platform.ingestion.service import IngestionService
from weather_platform.storage.jsonl import JsonlObservationStore
from weather_platform.storage.raw_objects import FileSystemRawObjectStore

ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = datetime(2026, 7, 21, 1, 30, tzinfo=UTC)


class FailingAdapter(ObservationAdapter):
    @property
    def adapter_id(self) -> str:
        return "failing-adapter/1.0.0"

    def decode(self, payload: bytes):  # type: ignore[no-untyped-def]
        raise ValueError("decoder rejected source record")


def make_service(tmp_path: Path) -> IngestionService:
    return IngestionService(
        FileSystemRawObjectStore(tmp_path / "raw"),
        JsonlObservationStore(tmp_path / "observations.jsonl"),
        clock=lambda: FIXED_TIME,
    )


def test_ingestion_stores_raw_before_decode_and_binds_provenance(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    payload = (ROOT / "testdata/observations/temperature.json").read_bytes()

    result = service.ingest(JsonObservationAdapter(), payload)
    stored = service.observation_store.list()

    assert result.raw_object.created is True
    assert result.observations_written == 1
    assert result.duplicate is False
    assert service.raw_store.get(result.raw_object.digest) == payload
    assert len(stored) == 1
    assert stored[0].observation_id == result.observation_ids[0]
    assert stored[0].provenance.source_record_digest == result.raw_object.digest
    assert stored[0].provenance.source_object_uri == result.raw_object.uri
    assert stored[0].provenance.decoder_version == "json-observation-adapter/0.2.0"
    assert stored[0].ingestion_time == FIXED_TIME
    assert stored[0].provenance.ingested_at == FIXED_TIME


def test_duplicate_source_and_decoder_is_idempotent(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    payload = (ROOT / "testdata/observations/temperature.json").read_bytes()

    first = service.ingest(JsonObservationAdapter(), payload)
    second = service.ingest(JsonObservationAdapter(), payload)

    assert first.observation_ids == second.observation_ids
    assert first.observations_written == 1
    assert second.raw_object.created is False
    assert second.observations_written == 0
    assert second.duplicate is True
    assert len(service.observation_store.list()) == 1


def test_raw_object_survives_decoder_failure(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    payload = b"malformed but evidentiary source bytes"
    digest = FileSystemRawObjectStore.digest(payload)

    with pytest.raises(ValueError, match="decoder rejected"):
        service.ingest(FailingAdapter(), payload)

    assert service.raw_store.get(digest) == payload
    assert service.observation_store.list() == []


def test_rejected_observation_is_not_canonical_but_raw_is_retained(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    payload = (ROOT / "testdata/observations/temperature.json").read_text()
    payload = payload.replace('"quality_disposition": "accept"', '"quality_disposition": "reject"')
    encoded = payload.encode()
    digest = FileSystemRawObjectStore.digest(encoded)

    with pytest.raises(ValueError, match="cannot enter"):
        service.ingest(JsonObservationAdapter(), encoded)

    assert service.raw_store.get(digest) == encoded
    assert service.observation_store.list() == []

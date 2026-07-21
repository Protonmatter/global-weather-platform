import json
from pathlib import Path

import pytest

from weather_platform.domain.models import Observation
from weather_platform.ingestion.adapters.json_observation import JsonObservationAdapter
from weather_platform.ingestion.base import ObservationAdapter
from weather_platform.ingestion.pipeline import SourceDecodeError, ingest_source_record
from weather_platform.provenance import sha256_digest
from weather_platform.storage.raw import RawSourceStore

ROOT = Path(__file__).resolve().parents[2]


def load_payload() -> bytes:
    return (ROOT / "testdata/observations/temperature.json").read_bytes()


def test_source_record_is_retained_and_bound_to_observations(tmp_path: Path) -> None:
    raw_store = RawSourceStore(tmp_path / "raw")
    payload = load_payload()
    result = ingest_source_record(payload, adapter=JsonObservationAdapter(), raw_store=raw_store)
    assert result.source_record_digest == sha256_digest(payload)
    assert raw_store.retrieve(result.source_record_digest) == payload
    assert len(result.observations) == 1
    assert result.observations[0].provenance.source_record_digest == result.source_record_digest


def test_client_digest_is_optional_and_superseded(tmp_path: Path) -> None:
    record = json.loads(load_payload())
    del record["provenance"]["source_record_digest"]
    payload = json.dumps(record).encode("utf-8")
    raw_store = RawSourceStore(tmp_path / "raw")
    result = ingest_source_record(payload, adapter=JsonObservationAdapter(), raw_store=raw_store)
    assert result.observations[0].provenance.source_record_digest == sha256_digest(payload)


def test_undecodable_record_is_retained_before_failing(tmp_path: Path) -> None:
    raw_store = RawSourceStore(tmp_path / "raw")
    payload = b"not-a-canonical-observation"
    with pytest.raises(SourceDecodeError, match="could not be decoded") as excinfo:
        ingest_source_record(payload, adapter=JsonObservationAdapter(), raw_store=raw_store)
    assert excinfo.value.digest == sha256_digest(payload)
    assert raw_store.retrieve(excinfo.value.digest) == payload


def test_observation_not_referencing_retained_record_fails(tmp_path: Path) -> None:
    class PassthroughAdapter(ObservationAdapter):
        """Keeps the client-asserted digest instead of stamping the payload digest."""

        def decode(self, payload: bytes) -> list[Observation]:
            return [Observation.model_validate_json(payload)]

    raw_store = RawSourceStore(tmp_path / "raw")
    synthetic_digest = json.loads(load_payload())["provenance"]["source_record_digest"]
    assert synthetic_digest != sha256_digest(load_payload())
    with pytest.raises(ValueError, match="does not reference the retained source record"):
        ingest_source_record(load_payload(), adapter=PassthroughAdapter(), raw_store=raw_store)

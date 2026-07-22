from datetime import UTC, datetime
from pathlib import Path

import pytest

from weather_platform.domain.models import QualityDisposition
from weather_platform.ingestion.grib_bufr import (
    DECODER_VERSION,
    ECCODES_DEFINITION_VERSION,
    DecodedField,
    GoldenCase,
    GoldenCorpusDrift,
    GribBufrAdapter,
    observation_signature,
    replay_golden_corpus,
)
from weather_platform.ingestion.pipeline import SourceDecodeError, ingest_source_record
from weather_platform.provenance import sha256_digest
from weather_platform.storage.raw import RawSourceStore

FIXED = datetime(2026, 7, 20, 18, 0, tzinfo=UTC)


def stub_decode(payload: bytes) -> list[DecodedField]:
    if payload == b"good-grib":
        return [
            DecodedField(
                phenomenon="air_temperature",
                value=302.15,
                unit="K",
                coordinates=(-74.006, 40.7128),
                observation_time=FIXED,
            )
        ]
    if payload == b"suspect-grib":
        return [
            DecodedField(
                phenomenon="air_temperature",
                value=999.0,
                unit="K",
                coordinates=(0.0, 0.0),
                observation_time=FIXED,
                quality_disposition=QualityDisposition.QUARANTINE,
                quality_flags=["range_suspect"],
            )
        ]
    raise ValueError("unparseable message")


def adapter(decode=stub_decode) -> GribBufrAdapter:
    return GribBufrAdapter(decode, source_id="test-centre", clock=lambda: FIXED)


def test_decoder_records_pinned_definition_table_version() -> None:
    observation = adapter().decode(b"good-grib")[0]
    assert observation.provenance.decoder_version == DECODER_VERSION
    assert ECCODES_DEFINITION_VERSION in observation.provenance.decoder_version


def test_malformed_message_is_rejected() -> None:
    with pytest.raises(ValueError, match="undecodable"):
        adapter().decode(b"not-a-message")


def test_malformed_message_is_retained_before_failing(tmp_path: Path) -> None:
    raw_store = RawSourceStore(tmp_path / "raw")
    with pytest.raises(SourceDecodeError) as excinfo:
        ingest_source_record(b"not-a-message", adapter=adapter(), raw_store=raw_store)
    assert raw_store.retrieve(excinfo.value.digest) == b"not-a-message"


def test_decodable_but_suspect_message_is_quarantined_not_rejected() -> None:
    observation = adapter().decode(b"suspect-grib")[0]
    assert observation.quality_disposition is QualityDisposition.QUARANTINE
    assert observation.quality_flags == ["range_suspect"]


def test_signature_is_stable_across_ingestion_times() -> None:
    early = GribBufrAdapter(stub_decode, source_id="c", clock=lambda: FIXED).decode(b"good-grib")[0]
    later_clock = datetime(2026, 7, 20, 23, 0, tzinfo=UTC)
    late = GribBufrAdapter(stub_decode, source_id="c", clock=lambda: later_clock).decode(
        b"good-grib"
    )[0]
    assert late.ingestion_time != early.ingestion_time
    assert observation_signature(early) == observation_signature(late)


def test_golden_corpus_replay_detects_drift() -> None:
    baseline = observation_signature(adapter().decode(b"good-grib")[0])
    case = GoldenCase(name="good-grib", signatures=[baseline])
    replay_golden_corpus(adapter(), [(b"good-grib", case)])  # no drift

    def drifted(payload: bytes) -> list[DecodedField]:
        fields = stub_decode(payload)
        return [f.model_copy(update={"value": 303.0}) for f in fields]

    with pytest.raises(GoldenCorpusDrift, match="drifted"):
        replay_golden_corpus(adapter(drifted), [(b"good-grib", case)])


def test_pipeline_integration_binds_digest_and_derives_id(tmp_path: Path) -> None:
    raw_store = RawSourceStore(tmp_path / "raw")
    result = ingest_source_record(b"good-grib", adapter=adapter(), raw_store=raw_store)
    assert result.source_record_digest == sha256_digest(b"good-grib")
    assert len(result.observations) == 1
    assert result.observations[0].provenance.source_record_digest == result.source_record_digest

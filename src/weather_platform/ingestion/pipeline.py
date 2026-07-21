from dataclasses import dataclass

from weather_platform.domain.models import Observation
from weather_platform.ingestion.base import ObservationAdapter
from weather_platform.storage.raw import RawSourceStore


class SourceDecodeError(ValueError):
    """Raised when a retained source record cannot be decoded."""

    def __init__(self, digest: str) -> None:
        super().__init__(f"retained source record {digest} could not be decoded")
        self.digest = digest


@dataclass(frozen=True)
class IngestResult:
    source_record_digest: str
    observations: list[Observation]


def ingest_source_record(
    payload: bytes,
    *,
    adapter: ObservationAdapter,
    raw_store: RawSourceStore,
) -> IngestResult:
    """Retain the source record, then decode it into canonical observations.

    Retention happens before interpretation, so undecodable records remain
    available for quarantine review. Every decoded observation must reference
    the retained record in its provenance.
    """
    digest = raw_store.store(payload)
    try:
        observations = adapter.decode(payload)
    except ValueError as exc:
        # Covers json.JSONDecodeError and pydantic.ValidationError, both ValueError
        # subclasses; adapter rejections are client decode failures, not faults.
        raise SourceDecodeError(digest) from exc
    for observation in observations:
        if observation.provenance.source_record_digest != digest:
            raise ValueError("decoded observation does not reference the retained source record")
    return IngestResult(source_record_digest=digest, observations=observations)

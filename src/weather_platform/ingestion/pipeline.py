import uuid
from dataclasses import dataclass

from weather_platform.domain.models import Observation
from weather_platform.ingestion.base import ObservationAdapter
from weather_platform.storage.raw import RawSourceStore

# Stable namespace for content-derived observation identifiers.
OBSERVATION_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "urn:weather:observation-id")


def derive_observation_id(source_record_digest: str, decoder_version: str, index: int) -> uuid.UUID:
    """Derive a deterministic observation id from the retained source record.

    Identical source bytes decoded by the same decoder version always yield the
    same id, so redelivery is idempotent by construction and distinct sources
    cannot collide except by hash collision. Re-decoding under a new decoder
    version yields a new id, matching "corrected interpretations become new
    derived records".
    """
    name = f"{source_record_digest}|{decoder_version}|{index}"
    return uuid.uuid5(OBSERVATION_ID_NAMESPACE, name)


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
    identified: list[Observation] = []
    for index, observation in enumerate(observations):
        if observation.provenance.source_record_digest != digest:
            raise ValueError("decoded observation does not reference the retained source record")
        # The canonical id is derived from the retained source, superseding any
        # id asserted in the payload, so identity is a function of content.
        observation_id = derive_observation_id(
            digest, observation.provenance.decoder_version, index
        )
        identified.append(observation.model_copy(update={"observation_id": observation_id}))
    return IngestResult(source_record_digest=digest, observations=identified)

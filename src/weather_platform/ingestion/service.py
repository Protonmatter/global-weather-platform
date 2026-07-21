from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid5

from weather_platform.domain.models import Observation, QualityDisposition
from weather_platform.ingestion.base import ObservationAdapter
from weather_platform.storage.jsonl import JsonlObservationStore
from weather_platform.storage.raw_objects import FileSystemRawObjectStore, RawObjectReference

_OBSERVATION_NAMESPACE = UUID("29bb64a5-91f5-4d13-b653-9d289f56bf7c")


@dataclass(frozen=True, slots=True)
class IngestionResult:
    raw_object: RawObjectReference
    observation_ids: tuple[UUID, ...]
    observations_written: int
    duplicate: bool


class IngestionService:
    """Store source bytes before decoding and bind derived records to the source object."""

    def __init__(
        self,
        raw_store: FileSystemRawObjectStore,
        observation_store: JsonlObservationStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.raw_store = raw_store
        self.observation_store = observation_store
        self.clock = clock or (lambda: datetime.now(UTC))

    def ingest(self, adapter: ObservationAdapter, payload: bytes) -> IngestionResult:
        raw_object = self.raw_store.put(payload)
        decoded = adapter.decode(payload)
        ingestion_time = self.clock()

        canonical: list[Observation] = []
        for index, observation in enumerate(decoded):
            if observation.quality_disposition in {
                QualityDisposition.QUARANTINE,
                QualityDisposition.REJECT,
            }:
                raise ValueError(
                    "quarantined or rejected observations cannot enter the canonical store"
                )

            deterministic_id = uuid5(
                _OBSERVATION_NAMESPACE,
                f"{raw_object.digest}:{adapter.adapter_id}:{index}",
            )
            provenance = observation.provenance.model_copy(
                update={
                    "source_record_digest": raw_object.digest,
                    "source_object_uri": raw_object.uri,
                    "ingested_at": ingestion_time,
                    "decoder_version": adapter.adapter_id,
                }
            )
            canonical.append(
                observation.model_copy(
                    update={
                        "observation_id": deterministic_id,
                        "ingestion_time": ingestion_time,
                        "provenance": provenance,
                    }
                )
            )

        written = self.observation_store.append_many(canonical)
        observation_ids = tuple(observation.observation_id for observation in canonical)
        return IngestionResult(
            raw_object=raw_object,
            observation_ids=observation_ids,
            observations_written=written,
            duplicate=bool(canonical) and written == 0,
        )

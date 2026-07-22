"""GRIB2/BUFR decoder service (DATA-003).

The low-level message decode is the ecCodes step; it requires the native
ecCodes library and its definition tables, so it is injected as a
``MessageDecoder`` rather than imported here. This module provides the decoder
*service* around it: a pinned, recorded definition-table version, canonical
observation construction, safe handling of malformed messages, and golden-corpus
replay that detects unexplained semantic drift when the decoder changes.
"""

import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from weather_platform.domain.models import (
    Observation,
    PointGeometry,
    Provenance,
    QualityDisposition,
    VerticalCoordinate,
)
from weather_platform.ingestion.base import ObservationAdapter

# Pinned ecCodes definition-table version, recorded in every observation's
# provenance so a table change is visible and auditable.
ECCODES_DEFINITION_VERSION = "eccodes-defs/2.34.0"
DECODER_VERSION = f"grib-bufr-decoder/0.1.0+{ECCODES_DEFINITION_VERSION}"


class DecodedField(BaseModel):
    """One field the ecCodes step extracts from a message, pre-canonicalization."""

    model_config = ConfigDict(extra="forbid")

    phenomenon: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    value: float | None
    unit: str = Field(min_length=1)
    coordinates: tuple[float, float] | tuple[float, float, float]
    observation_time: AwareDatetime
    vertical_coordinate: VerticalCoordinate | None = None
    quality_disposition: QualityDisposition = QualityDisposition.ACCEPT
    quality_flags: list[str] = Field(default_factory=list)


MessageDecoder = Callable[[bytes], list[DecodedField]]


class GoldenCorpusDrift(AssertionError):
    """Raised when a decoder replay diverges from the recorded golden output."""


def _digest(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


class GribBufrAdapter(ObservationAdapter):
    """Canonicalizes ecCodes-decoded fields into observations with pinned provenance."""

    def __init__(
        self,
        decode: MessageDecoder,
        *,
        source_id: str,
        clock: Callable[[], AwareDatetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._decode = decode
        self._source_id = source_id
        self._clock = clock

    def decode(self, payload: bytes) -> list[Observation]:
        try:
            fields = self._decode(payload)
        except Exception as exc:
            # An undecodable message is rejected safely; the raw record was
            # already retained upstream, so evidence is preserved.
            raise ValueError("undecodable GRIB/BUFR message") from exc
        digest = _digest(payload)
        ingested_at = self._clock()
        return [self._to_observation(field, digest, ingested_at) for field in fields]

    def _to_observation(
        self, field: DecodedField, digest: str, ingested_at: AwareDatetime
    ) -> Observation:
        return Observation(
            observation_id=_placeholder_id(digest),  # superseded by the pipeline's derived id
            phenomenon=field.phenomenon,
            value=field.value,
            unit=field.unit,
            geometry=PointGeometry(coordinates=field.coordinates),
            vertical_coordinate=field.vertical_coordinate,
            observation_time=field.observation_time,
            ingestion_time=ingested_at,
            quality_disposition=field.quality_disposition,
            quality_flags=field.quality_flags,
            provenance=Provenance(
                source_id=self._source_id,
                source_record_digest=digest,
                ingested_at=ingested_at,
                decoder_version=DECODER_VERSION,
            ),
        )


def _placeholder_id(digest: str) -> UUID:
    # The ingestion pipeline derives the canonical id from the source digest and
    # decoder version; this deterministic placeholder is superseded before storage.
    return uuid5(NAMESPACE_URL, f"urn:weather:grib:{digest}")


def observation_signature(observation: Observation) -> str:
    """A stable hash of an observation's decoded content, excluding volatile fields.

    Observation id (derived), ingestion time, and received time are runtime
    metadata, not decoded semantics, so they are excluded. Two decoder runs over
    the same bytes must produce the same signature.
    """
    content = observation.model_dump(
        mode="json",
        exclude={
            "observation_id": True,
            "ingestion_time": True,
            "provenance": {"ingested_at", "received_at"},
        },
    )
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class GoldenCase(BaseModel):
    """A recorded message and the signatures its decode must reproduce."""

    model_config = ConfigDict(extra="forbid")

    name: str
    signatures: list[str]


def replay_golden_corpus(
    adapter: GribBufrAdapter,
    cases: Sequence[tuple[bytes, GoldenCase]],
) -> None:
    """Decode each golden message and fail on any drift from its recorded signatures."""
    for payload, case in cases:
        observations = adapter.decode(payload)
        actual = [observation_signature(o) for o in observations]
        if actual != case.signatures:
            raise GoldenCorpusDrift(
                f"golden case {case.name} drifted: expected {case.signatures}, got {actual}"
            )

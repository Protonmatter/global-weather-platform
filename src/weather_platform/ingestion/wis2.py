import base64
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AnyUrl, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from weather_platform.domain.models import DigestVerification, Observation
from weather_platform.ingestion.base import ObservationAdapter
from weather_platform.ingestion.pipeline import ingest_source_record
from weather_platform.storage.raw import RawSourceStore

# {origin|cache}/a/wis2/{centre-id}/data/{core|recommended}/{domain...}: this
# consumer acquires data notifications only, so metadata channels and unknown
# notification types or data policies are rejected before any fetch.
WIS2_TOPIC = re.compile(
    r"^(origin|cache)/a/wis2/[a-z0-9-]+/data/(core|recommended)(/[a-z0-9._-]+)+$"
)


def validate_wis2_topic(topic: str) -> str:
    if not WIS2_TOPIC.match(topic):
        raise ValueError("topic is not a valid WIS2 data notification topic")
    return topic


class Wis2IntegrityMethod(StrEnum):
    SHA256 = "sha256"
    SHA384 = "sha384"
    SHA512 = "sha512"
    SHA3_256 = "sha3-256"
    SHA3_384 = "sha3-384"
    SHA3_512 = "sha3-512"

    @property
    def hashlib_name(self) -> str:
        # WIS2 spells SHA-3 methods with a hyphen; hashlib uses an underscore.
        return self.value.replace("-", "_")


class Wis2Integrity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    method: Wis2IntegrityMethod
    value: str = Field(min_length=1)


class Wis2Link(BaseModel):
    model_config = ConfigDict(extra="ignore")

    href: AnyUrl
    rel: str = Field(min_length=1)


WNM_CORE_CONFORMANCE = "http://wis.wmo.int/spec/wnm/1/conf/core"
LEGACY_WNM_VERSION = "v04"


Position = tuple[float, float] | tuple[float, float, float]


def _validate_position(position: Position) -> None:
    longitude, latitude = position[0], position[1]
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise ValueError("geometry position is outside longitude/latitude bounds")


class Wis2PointGeometry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["Point"]
    coordinates: Position

    @model_validator(mode="after")
    def validate_position(self) -> "Wis2PointGeometry":
        _validate_position(self.coordinates)
        return self


class Wis2PolygonGeometry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["Polygon"]
    coordinates: list[list[Position]]

    @model_validator(mode="after")
    def validate_rings(self) -> "Wis2PolygonGeometry":
        if not self.coordinates:
            raise ValueError("polygon geometry requires at least one ring")
        for ring in self.coordinates:
            if len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError("polygon rings require at least four positions and closure")
            for position in ring:
                _validate_position(position)
        return self


# WNM permits Point or Polygon geometry, or null on the notification.
Wis2Geometry = Wis2PointGeometry | Wis2PolygonGeometry


class Wis2Properties(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    data_id: str = Field(min_length=1)
    pubtime: AwareDatetime
    observed_datetime: AwareDatetime | None = Field(default=None, alias="datetime")
    start_datetime: AwareDatetime | None = None
    end_datetime: AwareDatetime | None = None
    integrity: Wis2Integrity | None = None

    @model_validator(mode="after")
    def validate_temporal_description(self) -> "Wis2Properties":
        # WNM temporal metadata is an exclusive choice: one instant or one
        # complete interval. Reject mixed and partial descriptions before fetch.
        bounds = (self.start_datetime is not None) + (self.end_datetime is not None)
        if self.observed_datetime is not None:
            if bounds != 0:
                raise ValueError(
                    "notification properties must not mix datetime with an interval"
                )
        elif bounds != 2:
            raise ValueError(
                "notification properties require datetime or both interval bounds"
            )
        return self


class Wis2Notification(BaseModel):
    """Subset of the WIS2 Notification Message needed for acquisition.

    Notifications are produced externally and evolve, so unknown fields are
    ignored rather than rejected; the required WNM envelope (GeoJSON geometry
    and a conformance marker) still gates every fetch.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: UUID
    type: str = Field(pattern="^Feature$")
    geometry: Wis2Geometry | None
    conforms_to: list[str] | None = Field(default=None, alias="conformsTo")
    version: str | None = None
    properties: Wis2Properties
    links: list[Wis2Link] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_envelope(self) -> "Wis2Notification":
        declares_core = self.conforms_to is not None and WNM_CORE_CONFORMANCE in self.conforms_to
        declares_legacy = self.version == LEGACY_WNM_VERSION
        if declares_core == declares_legacy:
            raise ValueError(
                "notification must declare exactly one WNM conformance marker: "
                f"conformsTo including {WNM_CORE_CONFORMANCE} or legacy version "
                f"{LEGACY_WNM_VERSION}"
            )
        canonical = [link for link in self.links if link.rel == "canonical"]
        if len(canonical) != 1:
            raise ValueError("notification must carry exactly one canonical link")
        # No acquisition path may fall back to unauthenticated transport
        # (DATA-004), and credentials never enter provenance records.
        href = canonical[0].href
        if href.scheme != "https" or href.username is not None or href.password is not None:
            raise ValueError("canonical link must use https without embedded credentials")
        return self

    @property
    def canonical_link(self) -> Wis2Link:
        return next(link for link in self.links if link.rel == "canonical")


class Wis2NotificationError(ValueError):
    """Raised when a retained notification cannot be interpreted."""

    def __init__(self, notification_digest: str) -> None:
        super().__init__(
            f"retained notification {notification_digest} is not a usable WIS2 message"
        )
        self.notification_digest = notification_digest


class Wis2IntegrityError(ValueError):
    """Raised when retained data does not match the notification's integrity claim."""

    def __init__(self, source_record_digest: str) -> None:
        super().__init__(
            f"retained source record {source_record_digest} failed upstream integrity verification"
        )
        self.source_record_digest = source_record_digest


@dataclass(frozen=True)
class Wis2IngestResult:
    notification_digest: str
    source_record_digest: str
    published_at: datetime
    received_at: datetime
    upstream_integrity_verified: bool
    observations: list[Observation]


class Wis2NotificationConsumer:
    """Transport-agnostic core of the WIS2 acquisition worker.

    The MQTT session and HTTP download live in the acquisition trust zone and
    are injected as the received bytes and the fetch callable, so this logic
    runs identically under test and in the worker.
    """

    def __init__(
        self,
        *,
        adapter: ObservationAdapter,
        raw_store: RawSourceStore,
        fetch: Callable[[str], bytes],
    ) -> None:
        self._adapter = adapter
        self._raw_store = raw_store
        self._fetch = fetch

    def process(
        self, topic: str, notification: bytes, received_at: AwareDatetime
    ) -> Wis2IngestResult:
        validate_wis2_topic(topic)
        if received_at.tzinfo is None:
            raise ValueError("received_at must be timezone-aware")
        # The notification is itself a source record: retain before interpretation.
        notification_digest = self._raw_store.store(notification)
        try:
            message = Wis2Notification.model_validate_json(notification)
        except ValueError as exc:
            raise Wis2NotificationError(notification_digest) from exc

        payload = self._fetch(str(message.canonical_link.href))
        # Retain the data bytes before integrity verification so a mismatch
        # leaves evidence of exactly what was received.
        source_record_digest = self._raw_store.store(payload)
        verified = self._verify_integrity(message, payload, source_record_digest)

        result = ingest_source_record(payload, adapter=self._adapter, raw_store=self._raw_store)
        observations = [
            self._bind_provenance(observation, message, received_at, verified=verified)
            for observation in result.observations
        ]
        return Wis2IngestResult(
            notification_digest=notification_digest,
            source_record_digest=result.source_record_digest,
            published_at=message.properties.pubtime,
            received_at=received_at,
            upstream_integrity_verified=verified,
            observations=observations,
        )

    @staticmethod
    def _verify_integrity(
        message: Wis2Notification, payload: bytes, source_record_digest: str
    ) -> bool:
        integrity = message.properties.integrity
        if integrity is None:
            return False
        try:
            claimed = base64.b64decode(integrity.value, validate=True)
        except ValueError as exc:
            raise Wis2IntegrityError(source_record_digest) from exc
        computed = hashlib.new(integrity.method.hashlib_name, payload).digest()
        if claimed != computed:
            raise Wis2IntegrityError(source_record_digest)
        return True

    @staticmethod
    def _bind_provenance(
        observation: Observation,
        message: Wis2Notification,
        received_at: AwareDatetime,
        *,
        verified: bool,
    ) -> Observation:
        provenance = observation.provenance.model_copy(
            update={
                "source_id": message.properties.data_id,
                "source_uri": message.canonical_link.href,
                "source_published_at": message.properties.pubtime,
                "received_at": received_at,
                # Durable trust state: whether the retained digest was confirmed
                # against upstream metadata or is platform-computed only.
                "digest_verification": (
                    DigestVerification.UPSTREAM if verified else DigestVerification.PLATFORM
                ),
            }
        )
        return observation.model_copy(update={"provenance": provenance})

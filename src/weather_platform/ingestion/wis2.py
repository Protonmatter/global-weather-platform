import base64
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import AnyUrl, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from weather_platform.domain.models import Observation
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


class Wis2Properties(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data_id: str = Field(min_length=1)
    pubtime: AwareDatetime
    integrity: Wis2Integrity | None = None


class Wis2Notification(BaseModel):
    """Subset of the WIS2 Notification Message needed for acquisition.

    Notifications are produced externally and evolve, so unknown fields are
    ignored rather than rejected.
    """

    model_config = ConfigDict(extra="ignore")

    id: UUID
    type: str = Field(pattern="^Feature$")
    properties: Wis2Properties
    links: list[Wis2Link] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_canonical_link(self) -> "Wis2Notification":
        canonical = [link for link in self.links if link.rel == "canonical"]
        if len(canonical) != 1:
            raise ValueError("notification must carry exactly one canonical link")
        # No acquisition path may fall back to unauthenticated transport (DATA-004).
        if canonical[0].href.scheme != "https":
            raise ValueError("canonical link must use https")
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
            self._bind_provenance(observation, message, received_at)
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
        observation: Observation, message: Wis2Notification, received_at: AwareDatetime
    ) -> Observation:
        provenance = observation.provenance.model_copy(
            update={
                "source_id": message.properties.data_id,
                "source_uri": message.canonical_link.href,
                "source_published_at": message.properties.pubtime,
                "received_at": received_at,
            }
        )
        return observation.model_copy(update={"provenance": provenance})

from datetime import datetime
from hashlib import sha256
from itertools import pairwise
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

SHA256_PATTERN = r"^sha256:[a-f0-9]{64}$"


def _sha256_digest(payload: bytes) -> str:
    return f"sha256:{sha256(payload).hexdigest()}"


class UpstreamObject(BaseModel):
    """Identity and size metadata for one provider object."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bucket: str = Field(min_length=1)
    key: str = Field(min_length=1)
    etag: str | None = None
    last_modified: AwareDatetime | None = None
    content_length: int = Field(gt=0)


class ByteSelection(BaseModel):
    """An inclusive byte interval selected from an upstream object."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    byte_start: int = Field(ge=0)
    byte_end: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.byte_end < self.byte_start:
            raise ValueError("byte_end must be greater than or equal to byte_start")
        return self

    @property
    def length(self) -> int:
        return self.byte_end - self.byte_start + 1


class SliceVerification(BaseModel):
    """Platform integrity evidence for a selectively retrieved source slice."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    index_digest: str = Field(pattern=SHA256_PATTERN)
    payload_digest: str = Field(pattern=SHA256_PATTERN)
    transport_verified: bool


class SourceSliceManifest(BaseModel):
    """Immutable acquisition context for one provider object byte range."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = "1.0.0"
    provider: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    product: str = Field(min_length=1)
    cycle: AwareDatetime
    forecast_hour: int = Field(ge=0)
    upstream: UpstreamObject
    selection: ByteSelection
    verification: SliceVerification
    discovered_at: AwareDatetime
    download_started_at: AwareDatetime
    received_at: AwareDatetime
    retained_at: AwareDatetime

    @classmethod
    def from_retained_bytes(
        cls,
        *,
        provider: str,
        dataset: str,
        product: str,
        cycle: datetime,
        forecast_hour: int,
        upstream: UpstreamObject,
        selection: ByteSelection,
        index_bytes: bytes,
        payload_bytes: bytes,
        transport_verified: bool,
        discovered_at: datetime,
        download_started_at: datetime,
        received_at: datetime,
        retained_at: datetime,
    ) -> Self:
        """Construct a manifest from retained evidence and computed digests."""

        if not index_bytes:
            raise ValueError("index bytes must not be empty")
        if len(payload_bytes) != selection.length:
            raise ValueError("payload length must equal selected byte range length")

        return cls(
            provider=provider,
            dataset=dataset,
            product=product,
            cycle=cycle,
            forecast_hour=forecast_hour,
            upstream=upstream,
            selection=selection,
            verification=SliceVerification(
                index_digest=_sha256_digest(index_bytes),
                payload_digest=_sha256_digest(payload_bytes),
                transport_verified=transport_verified,
            ),
            discovered_at=discovered_at,
            download_started_at=download_started_at,
            received_at=received_at,
            retained_at=retained_at,
        )

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if self.selection.byte_end >= self.upstream.content_length:
            raise ValueError("selected byte range exceeds upstream content length")

        timestamps = (
            self.discovered_at,
            self.download_started_at,
            self.received_at,
            self.retained_at,
        )
        if any(later < earlier for earlier, later in pairwise(timestamps)):
            raise ValueError("acquisition timestamps must be monotonic")
        return self

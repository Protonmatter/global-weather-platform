from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QualityDisposition(StrEnum):
    ACCEPT = "accept"
    ACCEPT_WITH_FLAGS = "accept_with_flags"
    QUARANTINE = "quarantine"
    REJECT = "reject"


class PointGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(default="Point", pattern="^Point$")
    coordinates: tuple[float, float] | tuple[float, float, float]

    @model_validator(mode="after")
    def validate_coordinates(self) -> "PointGeometry":
        longitude, latitude = self.coordinates[:2]
        if not -180 <= longitude <= 180:
            raise ValueError("longitude must be in [-180, 180]")
        if not -90 <= latitude <= 90:
            raise ValueError("latitude must be in [-90, 90]")
        return self


class VerticalCoordinate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    value: float
    unit: str


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_uri: str | None = None
    source_published_at: datetime | None = None
    source_record_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source_object_uri: str = Field(pattern=r"^cas://sha256/[a-f0-9]{64}$")
    ingested_at: datetime
    decoder_version: str
    license_id: str | None = None


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0.0"
    observation_id: UUID
    phenomenon: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    value: float | None
    unit: str = Field(min_length=1)
    uncertainty: float | None = Field(default=None, ge=0)
    trace: bool = False
    geometry: PointGeometry
    vertical_coordinate: VerticalCoordinate | None = None
    observation_time: datetime
    ingestion_time: datetime
    quality_disposition: QualityDisposition
    quality_flags: list[str] = Field(default_factory=list)
    provenance: Provenance

    @model_validator(mode="after")
    def validate_missingness(self) -> "Observation":
        if self.value is None and self.trace:
            raise ValueError("trace cannot be true when value is missing")
        if self.quality_disposition == QualityDisposition.ACCEPT and self.quality_flags:
            raise ValueError("accepted observations cannot carry unresolved quality flags")
        return self

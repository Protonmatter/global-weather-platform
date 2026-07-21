from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import (
    AnyUrl,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class QualityDisposition(StrEnum):
    ACCEPT = "accept"
    ACCEPT_WITH_FLAGS = "accept_with_flags"
    QUARANTINE = "quarantine"
    REJECT = "reject"


class VerticalCoordinateType(StrEnum):
    HEIGHT = "height"
    PRESSURE = "pressure"
    DEPTH = "depth"
    MODEL_LEVEL = "model_level"


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

    type: VerticalCoordinateType
    value: float
    unit: str


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    source_uri: AnyUrl | None = None
    source_published_at: AwareDatetime | None = None
    source_record_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    ingested_at: AwareDatetime
    decoder_version: str = Field(min_length=1)
    license_id: str | None = None


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"] = "1.0.0"
    observation_id: UUID
    phenomenon: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    value: float | None
    unit: str = Field(min_length=1)
    uncertainty: float | None = Field(default=None, ge=0)
    trace: bool = False
    geometry: PointGeometry
    vertical_coordinate: VerticalCoordinate | None = None
    observation_time: AwareDatetime
    ingestion_time: AwareDatetime
    quality_disposition: QualityDisposition
    quality_flags: list[str] = Field(default_factory=list)
    provenance: Provenance

    @field_validator("quality_flags")
    @classmethod
    def validate_quality_flags_unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("quality flags must be unique")
        return value

    @model_validator(mode="after")
    def validate_missingness(self) -> "Observation":
        if self.value is None and self.trace:
            raise ValueError("trace cannot be true when value is missing")
        if self.quality_disposition == QualityDisposition.ACCEPT and self.quality_flags:
            raise ValueError("accepted observations cannot carry unresolved quality flags")
        return self

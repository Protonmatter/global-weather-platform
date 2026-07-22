from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class GuidanceOrigin(StrEnum):
    """The program charter's four-way guidance distinction (PROG-GOV-0001).

    Every catalogued cycle is labeled so official warnings, imported provider
    guidance, platform-generated guidance, and experimental output are never
    conflated.
    """

    OFFICIAL_WARNING = "official_warning"
    IMPORTED = "imported"
    PLATFORM = "platform"
    EXPERIMENTAL = "experimental"


class CycleCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"


class ModelCycleField(BaseModel):
    """One indexed slot of a model cycle: a variable at a level, grid, and lead."""

    model_config = ConfigDict(extra="forbid")

    variable: str = Field(min_length=1)
    level_type: str = Field(min_length=1)
    level_value: float | None = None
    grid: str = Field(min_length=1)
    lead_hours: int = Field(ge=0)
    member: str | None = None

    def key(self) -> tuple[str, str, float | None, str, int, str | None]:
        return (
            self.variable,
            self.level_type,
            self.level_value,
            self.grid,
            self.lead_hours,
            self.member,
        )


class ModelGuidanceCycle(BaseModel):
    """A catalogued external or platform model cycle and its field inventory."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0.0"
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    guidance_origin: GuidanceOrigin
    initialized_at: AwareDatetime
    source_revision: str = Field(min_length=1)
    grids: list[str] = Field(min_length=1)
    expected_fields: list[ModelCycleField] = Field(min_length=1)
    available_fields: list[ModelCycleField] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_inventory(self) -> "ModelGuidanceCycle":
        expected = {field.key() for field in self.expected_fields}
        if len(expected) != len(self.expected_fields):
            raise ValueError("expected_fields must not contain duplicates")
        for field in self.available_fields:
            if field.key() not in expected:
                raise ValueError("available_fields must be a subset of expected_fields")
            if field.grid not in self.grids:
                raise ValueError("available field references a grid not declared on the cycle")
        return self

    def cycle_key(self) -> tuple[str, str, str, str]:
        return (
            self.model_id,
            self.model_version,
            self.initialized_at.isoformat(),
            self.source_revision,
        )

    def missing_fields(self) -> list[ModelCycleField]:
        available = {field.key() for field in self.available_fields}
        return [field for field in self.expected_fields if field.key() not in available]

    def completeness(self) -> CycleCompleteness:
        if not self.available_fields:
            return CycleCompleteness.MISSING
        if self.missing_fields():
            return CycleCompleteness.PARTIAL
        return CycleCompleteness.COMPLETE

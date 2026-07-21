from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WEATHER_", env_file=".env", extra="ignore")

    environment: str = "development"
    data_dir: Path = Path("./data")
    log_level: str = "INFO"
    internal_otel_endpoint: str | None = None
    allow_external_egress: bool = False

    @field_validator("internal_otel_endpoint")
    @classmethod
    def validate_internal_otel_endpoint(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        permitted = ("http://otel-collector.", "https://otel-collector.", "http://localhost:")
        if not value.startswith(permitted):
            raise ValueError("OpenTelemetry endpoint must identify an approved internal collector")
        return value

    data_filename: str = Field(default="observations.jsonl", exclude=True)
    raw_object_subdirectory: str = Field(default="raw-objects", exclude=True)
    max_raw_object_bytes: int = Field(default=64 * 1024 * 1024, gt=0)

    @property
    def observation_path(self) -> Path:
        return self.data_dir / self.data_filename

    @property
    def raw_object_dir(self) -> Path:
        return self.data_dir / self.raw_object_subdirectory

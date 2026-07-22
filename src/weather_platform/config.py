import re
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from weather_platform.storage.raw import DEFAULT_MAX_SOURCE_RECORD_BYTES

INTERNAL_COLLECTOR_HOST = re.compile(
    r"^otel-collector\.[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.svc(\.cluster\.local)?)?$"
)
MIN_MAX_SOURCE_RECORD_BYTES = 8192


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WEATHER_", env_file=".env", extra="ignore")

    environment: str = "development"
    data_dir: Path = Path("./data")
    log_level: str = "INFO"
    internal_otel_endpoint: str | None = None
    allow_external_egress: bool = False
    # The deployment-wide source bound must still accommodate the complete
    # WIS2 notification envelope retained before interpretation.
    max_source_record_bytes: int = Field(
        default=DEFAULT_MAX_SOURCE_RECORD_BYTES,
        ge=MIN_MAX_SOURCE_RECORD_BYTES,
    )

    @field_validator("internal_otel_endpoint")
    @classmethod
    def validate_internal_otel_endpoint(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        parts = urlsplit(value)
        hostname = parts.hostname or ""
        allowed_host = hostname == "localhost" or INTERNAL_COLLECTOR_HOST.match(hostname)
        if parts.scheme not in {"http", "https"} or not allowed_host or parts.username is not None:
            raise ValueError("OpenTelemetry endpoint must identify an approved internal collector")
        return value

    data_filename: str = Field(default="observations.jsonl", exclude=True)

    @property
    def observation_path(self) -> Path:
        return self.data_dir / self.data_filename

    @property
    def raw_source_dir(self) -> Path:
        return self.data_dir / "raw"

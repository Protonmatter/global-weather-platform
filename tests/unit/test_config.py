import pytest
from pydantic import ValidationError

from weather_platform.config import Settings


def test_telemetry_is_disabled_by_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.internal_otel_endpoint is None


def test_public_otel_endpoint_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, internal_otel_endpoint="https://telemetry.example.com/v1/traces")


def test_internal_otel_endpoint_is_accepted() -> None:
    settings = Settings(
        _env_file=None, internal_otel_endpoint="http://otel-collector.monitoring:4318"
    )
    assert settings.internal_otel_endpoint is not None


def test_raw_object_defaults_are_internal_to_data_directory() -> None:
    settings = Settings(_env_file=None)
    assert settings.raw_object_dir == settings.data_dir / "raw-objects"
    assert settings.max_raw_object_bytes == 64 * 1024 * 1024

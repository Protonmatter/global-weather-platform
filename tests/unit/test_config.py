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
    for endpoint in (
        "http://otel-collector.monitoring:4318",
        "http://otel-collector.monitoring.svc.cluster.local:4318",
        "http://localhost:4318",
    ):
        settings = Settings(_env_file=None, internal_otel_endpoint=endpoint)
        assert settings.internal_otel_endpoint == endpoint


def test_lookalike_collector_host_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            internal_otel_endpoint="https://otel-collector.attacker.example/v1/traces",
        )


def test_collector_endpoint_with_credentials_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            internal_otel_endpoint="http://user:secret@otel-collector.monitoring:4318",
        )


def test_source_record_limit_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_source_record_bytes=0)

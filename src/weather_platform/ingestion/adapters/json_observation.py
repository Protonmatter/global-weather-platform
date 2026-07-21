from weather_platform.domain.models import Observation
from weather_platform.ingestion.base import ObservationAdapter


class JsonObservationAdapter(ObservationAdapter):
    """Reference adapter used for schema and pipeline testing."""

    @property
    def adapter_id(self) -> str:
        return "json-observation-adapter/0.2.0"

    def decode(self, payload: bytes) -> list[Observation]:
        return [Observation.model_validate_json(payload)]

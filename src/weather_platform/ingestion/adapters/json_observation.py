from weather_platform.domain.models import Observation
from weather_platform.ingestion.base import ObservationAdapter


class JsonObservationAdapter(ObservationAdapter):
    """Reference adapter used for schema and pipeline testing."""

    def decode(self, payload: bytes) -> list[Observation]:
        return [Observation.model_validate_json(payload)]

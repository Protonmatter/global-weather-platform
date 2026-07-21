from weather_platform.domain.models import Observation
from weather_platform.ingestion.base import ObservationAdapter
from weather_platform.provenance import sha256_digest


class JsonObservationAdapter(ObservationAdapter):
    """Reference adapter used for schema and pipeline testing.

    The received payload is the source record, so its digest supersedes any
    client-asserted source_record_digest in the payload.
    """

    def decode(self, payload: bytes) -> list[Observation]:
        observation = Observation.model_validate_json(payload)
        provenance = observation.provenance.model_copy(
            update={"source_record_digest": sha256_digest(payload)}
        )
        return [observation.model_copy(update={"provenance": provenance})]

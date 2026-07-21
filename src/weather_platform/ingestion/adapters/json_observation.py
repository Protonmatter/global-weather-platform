import json

from weather_platform.domain.models import Observation
from weather_platform.ingestion.base import ObservationAdapter
from weather_platform.provenance import sha256_digest


class JsonObservationAdapter(ObservationAdapter):
    """Reference adapter used for schema and pipeline testing.

    The received payload is the source record, so its digest is stamped into
    provenance before validation; a client-asserted source_record_digest is
    optional and superseded.
    """

    def decode(self, payload: bytes) -> list[Observation]:
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("source record must be a JSON object")
        provenance = data.get("provenance")
        if isinstance(provenance, dict):
            provenance["source_record_digest"] = sha256_digest(payload)
        return [Observation.model_validate(data)]

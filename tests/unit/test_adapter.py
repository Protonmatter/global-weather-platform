from pathlib import Path

from weather_platform.ingestion.adapters.json_observation import JsonObservationAdapter

ROOT = Path(__file__).resolve().parents[2]


def test_json_adapter_decodes_canonical_observation() -> None:
    payload = (ROOT / "testdata/observations/temperature.json").read_bytes()
    observations = JsonObservationAdapter().decode(payload)
    assert len(observations) == 1
    assert observations[0].phenomenon == "air_temperature"
    assert JsonObservationAdapter().adapter_id == "json-observation-adapter/0.2.0"

import json
from pathlib import Path

from weather_platform.domain.models import Observation
from weather_platform.storage.jsonl import JsonlObservationStore

ROOT = Path(__file__).resolve().parents[2]


def test_append_and_filter(tmp_path: Path) -> None:
    record = json.loads((ROOT / "testdata/observations/temperature.json").read_text())
    observation = Observation.model_validate(record)
    store = JsonlObservationStore(tmp_path / "observations.jsonl")
    assert store.append(observation) is True
    assert store.append(observation) is False
    assert store.list(phenomenon="air_temperature") == [observation]
    assert store.list(phenomenon="wind_speed") == []


def test_store_limit_and_compaction(tmp_path: Path) -> None:
    record = json.loads((ROOT / "testdata/observations/temperature.json").read_text())
    observation = Observation.model_validate(record)
    path = tmp_path / "observations.jsonl"
    store = JsonlObservationStore(path)
    store.append(observation)
    store.compact_atomically()
    assert store.list(limit=1) == [observation]
    import pytest

    with pytest.raises(ValueError, match="limit"):
        store.list(limit=0)


def test_store_reports_corrupt_line(tmp_path: Path) -> None:
    import pytest

    path = tmp_path / "observations.jsonl"
    path.write_text("not-json\n", encoding="utf-8")
    store = JsonlObservationStore(path)
    with pytest.raises(ValueError, match="line 1"):
        list(store.iter_observations())


def test_empty_store(tmp_path: Path) -> None:
    store = JsonlObservationStore(tmp_path / "missing.jsonl")
    assert store.list() == []

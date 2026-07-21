import math

from weather_platform.scientific.scores import brier_score, crps_ensemble, reliability_bins


def test_brier_score() -> None:
    assert math.isclose(brier_score(0.8, True), 0.04)
    assert math.isclose(brier_score(0.2, False), 0.04)


def test_crps_ensemble_for_perfect_single_member() -> None:
    assert crps_ensemble([4.0], 4.0) == 0.0


def test_crps_rewards_closer_ensemble() -> None:
    assert crps_ensemble([2.0, 3.0, 4.0], 3.0) < crps_ensemble([8.0, 9.0, 10.0], 3.0)


def test_reliability_bins_preserve_empty_bins() -> None:
    result = reliability_bins([0.1, 0.2, 0.9], [False, True, True], bins=5)
    assert len(result) == 5
    assert sum(int(item["count"]) for item in result) == 3


def test_score_input_validation() -> None:
    import pytest

    with pytest.raises(ValueError, match="ensemble member"):
        crps_ensemble([], 1.0)
    with pytest.raises(ValueError, match="finite"):
        crps_ensemble([float("nan")], 1.0)
    with pytest.raises(ValueError, match="equal length"):
        reliability_bins([0.5], [])
    with pytest.raises(ValueError, match="at least 2"):
        reliability_bins([0.5], [True], bins=1)

import math

import pytest

from weather_platform.scientific.probability import (
    dependence_adjusted_weights,
    effective_ensemble_size,
    normalize_weights,
    validate_quantiles,
)


def test_quantiles_are_monotonic() -> None:
    validate_quantiles([(0.1, 2.0), (0.5, 4.0), (0.9, 8.0)])
    with pytest.raises(ValueError, match="nondecreasing"):
        validate_quantiles([(0.1, 2.0), (0.5, 1.0)])


def test_weights_normalize_and_effective_size() -> None:
    assert normalize_weights([2.0, 2.0]) == [0.5, 0.5]
    assert math.isclose(effective_ensemble_size([1.0, 1.0, 1.0]), 3.0)
    assert math.isclose(effective_ensemble_size([1.0, 0.0, 0.0]), 1.0)


def test_dependence_penalizes_correlated_candidate() -> None:
    weights = dependence_adjusted_weights(
        losses=[0.2, 0.2],
        mean_error_correlations=[0.9, 0.1],
        dependence_penalty=2.0,
    )
    assert weights[1] > weights[0]
    assert math.isclose(sum(weights), 1.0)


def test_invalid_probability_and_weights_fail_closed() -> None:
    with pytest.raises(ValueError, match="probability"):
        validate_quantiles([(1.0, 2.0)])
    with pytest.raises(ValueError, match="weight sum"):
        normalize_weights([0.0, 0.0])
    with pytest.raises(ValueError, match="nonnegative"):
        normalize_weights([1.0, -1.0])


def test_dependence_weight_input_validation() -> None:
    with pytest.raises(ValueError, match="same nonzero length"):
        dependence_adjusted_weights([0.1], [])
    with pytest.raises(ValueError, match="invalid scaling"):
        dependence_adjusted_weights([0.1], [0.0], loss_scale=0.0)
    with pytest.raises(ValueError, match="losses"):
        dependence_adjusted_weights([-0.1], [0.0])
    with pytest.raises(ValueError, match="correlations"):
        dependence_adjusted_weights([0.1], [2.0])

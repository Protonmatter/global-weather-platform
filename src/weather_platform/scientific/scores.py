import math
from collections.abc import Sequence

from weather_platform.scientific.probability import validate_probability


def brier_score(probability: float, observed: bool) -> float:
    """Proper score for a binary probabilistic forecast; lower is better."""
    probability = validate_probability(probability)
    outcome = 1.0 if observed else 0.0
    return (probability - outcome) ** 2


def crps_ensemble(members: Sequence[float], observation: float, *, fair: bool = False) -> float:
    """Continuous ranked probability score for an empirical ensemble.

    CRPS = mean(|x_i-y|) - 0.5 * mean(|x_i-x_j|)

    The default estimator divides the pairwise term by n^2 and is biased low in
    spread for small ensembles; fair=True divides by n(n-1), which is unbiased
    and required when comparing ensembles of different sizes.
    """
    if not members:
        raise ValueError("at least one ensemble member is required")
    if fair and len(members) < 2:
        raise ValueError("fair CRPS requires at least two ensemble members")
    if not math.isfinite(observation) or any(not math.isfinite(value) for value in members):
        raise ValueError("members and observation must be finite")

    count = len(members)
    observation_term = math.fsum(abs(value - observation) for value in members) / count
    pairwise = math.fsum(abs(left - right) for left in members for right in members)
    denominator = count * (count - 1) if fair else count * count
    ensemble_term = pairwise / (2.0 * denominator)
    return observation_term - ensemble_term


def reliability_bins(
    probabilities: Sequence[float],
    outcomes: Sequence[bool],
    *,
    bins: int = 10,
) -> list[dict[str, float | int | None]]:
    if len(probabilities) != len(outcomes):
        raise ValueError("probabilities and outcomes must have equal length")
    if bins < 2:
        raise ValueError("bins must be at least 2")

    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for probability, outcome in zip(probabilities, outcomes, strict=True):
        probability = validate_probability(probability)
        index = min(int(probability * bins), bins - 1)
        buckets[index].append((probability, outcome))

    result: list[dict[str, float | int | None]] = []
    for index, bucket in enumerate(buckets):
        lower = index / bins
        upper = (index + 1) / bins
        if not bucket:
            result.append(
                {
                    "lower": lower,
                    "upper": upper,
                    "count": 0,
                    "forecast_mean": None,
                    "observed_frequency": None,
                }
            )
            continue
        result.append(
            {
                "lower": lower,
                "upper": upper,
                "count": len(bucket),
                "forecast_mean": math.fsum(item[0] for item in bucket) / len(bucket),
                "observed_frequency": (
                    math.fsum(1.0 if item[1] else 0.0 for item in bucket) / len(bucket)
                ),
            }
        )
    return result

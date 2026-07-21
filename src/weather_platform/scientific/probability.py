import math
from collections.abc import Sequence


def validate_probability(value: float) -> float:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("probability must be finite and in [0, 1]")
    return value


def validate_quantiles(quantiles: Sequence[tuple[float, float]]) -> None:
    """Validate strictly increasing probability levels and nondecreasing values."""
    if not quantiles:
        raise ValueError("at least one quantile is required")
    previous_probability = -math.inf
    previous_value = -math.inf
    for probability, value in quantiles:
        validate_probability(probability)
        if probability in (0.0, 1.0):
            raise ValueError("quantile probability must be strictly inside (0, 1)")
        if probability <= previous_probability:
            raise ValueError("quantile probabilities must be strictly increasing")
        if not math.isfinite(value):
            raise ValueError("quantile values must be finite")
        if value < previous_value:
            raise ValueError("quantile values must be nondecreasing")
        previous_probability = probability
        previous_value = value


def normalize_weights(weights: Sequence[float]) -> list[float]:
    if not weights:
        raise ValueError("at least one weight is required")
    if any((not math.isfinite(weight) or weight < 0.0) for weight in weights):
        raise ValueError("weights must be finite and nonnegative")
    total = math.fsum(weights)
    if total <= 0.0:
        raise ValueError("weight sum must be positive")
    return [weight / total for weight in weights]


def effective_ensemble_size(weights: Sequence[float]) -> float:
    """Return Kish effective sample size for normalized or unnormalized weights."""
    normalized = normalize_weights(weights)
    return 1.0 / math.fsum(weight * weight for weight in normalized)


def dependence_adjusted_weights(
    losses: Sequence[float],
    mean_error_correlations: Sequence[float],
    *,
    loss_scale: float = 1.0,
    dependence_penalty: float = 1.0,
) -> list[float]:
    """Create transparent initial fusion weights.

    Lower loss is preferred. Positive mean error correlation is penalized. This is
    only a baseline; operational fusion requires regime- and lead-conditioned
    validation and locked prospective evaluation.
    """
    if len(losses) != len(mean_error_correlations) or not losses:
        raise ValueError("losses and correlations must have the same nonzero length")
    if loss_scale <= 0.0 or dependence_penalty < 0.0:
        raise ValueError("invalid scaling parameters")

    logits: list[float] = []
    for loss, correlation in zip(losses, mean_error_correlations, strict=True):
        if not math.isfinite(loss) or loss < 0.0:
            raise ValueError("losses must be finite and nonnegative")
        if not math.isfinite(correlation) or not -1.0 <= correlation <= 1.0:
            raise ValueError("correlations must be finite and in [-1, 1]")
        logits.append(-(loss_scale * loss) - dependence_penalty * max(correlation, 0.0))

    maximum = max(logits)
    raw = [math.exp(logit - maximum) for logit in logits]
    return normalize_weights(raw)

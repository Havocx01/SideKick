"""Interval estimates.

Twenty held-out engines cannot support a confident point estimate, so every
engine-counting proportion the prototype reports carries an interval. Wilson is
used rather than the normal approximation because it behaves sensibly at the small
counts and near-0/near-1 proportions this evaluation actually produces.
"""

from __future__ import annotations

import math

from app.schemas import WilsonInterval

#: Two-sided standard normal quantiles for the levels we report.
_Z = {0.90: 1.6448536269514722, 0.95: 1.959963984540054, 0.99: 2.5758293035489004}


def z_for(level: float) -> float:
    if level in _Z:
        return _Z[level]
    try:
        from scipy.stats import norm
    except ImportError as exc:  # pragma: no cover
        raise ValueError(f"unsupported confidence level {level}") from exc
    return float(norm.ppf(0.5 + level / 2.0))


def wilson_interval(successes: int, trials: int, level: float = 0.95) -> WilsonInterval:
    """Wilson score interval for a binomial proportion.

    Returns the full ``[0, 1]`` range when there are no trials, which is the
    honest statement that nothing is known rather than a false zero.
    """
    if trials <= 0:
        return WilsonInterval(lower=0.0, upper=1.0, level=level)
    successes = max(0, min(int(successes), int(trials)))

    z = z_for(level)
    n = float(trials)
    phat = successes / n
    denominator = 1.0 + z * z / n
    centre = (phat + z * z / (2.0 * n)) / denominator
    spread = (z / denominator) * math.sqrt(phat * (1.0 - phat) / n + z * z / (4.0 * n * n))
    return WilsonInterval(
        lower=max(0.0, centre - spread),
        upper=min(1.0, centre + spread),
        level=level,
    )


def intervals_overlap(a: WilsonInterval, b: WilsonInterval) -> bool:
    """Whether two intervals overlap, i.e. the ordering is not established."""
    return a.lower <= b.upper and b.lower <= a.upper

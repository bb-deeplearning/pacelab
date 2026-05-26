"""Pure-function statistical helpers used across the metrics package."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Estimate:
    """A point estimate with a confidence interval and a sample size."""

    value: float
    ci_lo: float
    ci_hi: float
    n: int

    def to_dict(self) -> dict[str, float | int]:
        return {"value": self.value, "ci_lo": self.ci_lo, "ci_hi": self.ci_hi, "n": self.n}


def bootstrap_median_ci(
    values: np.ndarray,
    n_resamples: int = 10_000,
    alpha: float = 0.05,
    seed: int = 0,
) -> Estimate:
    """Percentile bootstrap CI for the median.

    Returns an Estimate with the empirical median and a (1-alpha) CI.
    For n < 3 returns an Estimate whose CI is (median, median) — the caller
    should render this with a "low sample" indicator.
    """
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    n = len(values)
    if n == 0:
        return Estimate(value=float("nan"), ci_lo=float("nan"), ci_hi=float("nan"), n=0)
    med = float(np.median(values))
    if n < 3:
        return Estimate(value=med, ci_lo=med, ci_hi=med, n=n)
    rng = np.random.default_rng(seed)
    resamples = rng.choice(values, size=(n_resamples, n), replace=True)
    medians = np.median(resamples, axis=1)
    lo = float(np.quantile(medians, alpha / 2))
    hi = float(np.quantile(medians, 1 - alpha / 2))
    return Estimate(value=med, ci_lo=lo, ci_hi=hi, n=n)


def bootstrap_mean_ci(
    values: np.ndarray,
    n_resamples: int = 10_000,
    alpha: float = 0.05,
    seed: int = 0,
) -> Estimate:
    """Percentile bootstrap CI for the mean."""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    n = len(values)
    if n == 0:
        return Estimate(value=float("nan"), ci_lo=float("nan"), ci_hi=float("nan"), n=0)
    mean = float(np.mean(values))
    if n < 3:
        return Estimate(value=mean, ci_lo=mean, ci_hi=mean, n=n)
    rng = np.random.default_rng(seed)
    resamples = rng.choice(values, size=(n_resamples, n), replace=True)
    means = np.mean(resamples, axis=1)
    lo = float(np.quantile(means, alpha / 2))
    hi = float(np.quantile(means, 1 - alpha / 2))
    return Estimate(value=mean, ci_lo=lo, ci_hi=hi, n=n)


def fit_linear_pace(stint_age: np.ndarray, lap_time_s: np.ndarray) -> tuple[float, float]:
    """OLS fit of lap_time = α + β · stint_age. Returns (alpha, beta).

    α is the predicted lap time at stint_age=0, β is the per-lap degradation slope.
    Falls back to (mean, 0.0) if fewer than 3 data points or numerically degenerate.
    """
    x = np.asarray(stint_age, dtype=float)
    y = np.asarray(lap_time_s, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 3:
        return (float(np.mean(y)) if len(y) else float("nan"), 0.0)
    x_mean = x.mean()
    y_mean = y.mean()
    denom = np.sum((x - x_mean) ** 2)
    if denom <= 0:
        return (float(y_mean), 0.0)
    beta = float(np.sum((x - x_mean) * (y - y_mean)) / denom)
    alpha = float(y_mean - beta * x_mean)
    return (alpha, beta)


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    """Weighted median. Returns NaN if no positive-weight entries."""
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    mask = np.isfinite(v) & np.isfinite(w) & (w > 0)
    v, w = v[mask], w[mask]
    if len(v) == 0:
        return float("nan")
    order = np.argsort(v)
    v_sorted = v[order]
    w_sorted = w[order]
    cum = np.cumsum(w_sorted)
    cutoff = cum[-1] / 2.0
    idx = np.searchsorted(cum, cutoff)
    return float(v_sorted[min(idx, len(v_sorted) - 1)])


__all__ = [
    "Estimate",
    "bootstrap_median_ci",
    "bootstrap_mean_ci",
    "fit_linear_pace",
    "weighted_median",
]

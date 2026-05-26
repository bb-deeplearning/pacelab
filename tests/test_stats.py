"""Tests for the pure statistical helpers."""

from __future__ import annotations

import numpy as np
import pytest

from pacelab.metrics.stats import (
    Estimate,
    bootstrap_mean_ci,
    bootstrap_median_ci,
    fit_linear_pace,
    weighted_median,
)


def test_bootstrap_median_handles_empty() -> None:
    est = bootstrap_median_ci(np.array([]))
    assert est.n == 0
    assert np.isnan(est.value)


def test_bootstrap_median_handles_single() -> None:
    est = bootstrap_median_ci(np.array([1.5]))
    assert est.n == 1
    assert est.value == 1.5
    assert est.ci_lo == est.ci_hi == 1.5


def test_bootstrap_median_central_tendency() -> None:
    rng = np.random.default_rng(42)
    sample = rng.normal(loc=2.0, scale=0.5, size=200)
    est = bootstrap_median_ci(sample, seed=42)
    assert est.n == 200
    assert abs(est.value - 2.0) < 0.1
    assert est.ci_lo < est.value < est.ci_hi


def test_bootstrap_mean_central_tendency() -> None:
    rng = np.random.default_rng(0)
    sample = rng.normal(loc=-0.3, scale=0.2, size=500)
    est = bootstrap_mean_ci(sample, seed=0)
    assert abs(est.value + 0.3) < 0.05
    assert est.ci_lo < est.value < est.ci_hi


def test_fit_linear_pace_recovers_slope() -> None:
    rng = np.random.default_rng(7)
    x = np.arange(30, dtype=float)
    y = 90.0 + 0.05 * x + rng.normal(0, 0.01, size=len(x))
    alpha, beta = fit_linear_pace(x, y)
    assert abs(beta - 0.05) < 0.005
    assert abs(alpha - 90.0) < 0.05


def test_fit_linear_pace_handles_too_few_points() -> None:
    alpha, beta = fit_linear_pace(np.array([1.0, 2.0]), np.array([90.0, 91.0]))
    assert beta == 0.0  # falls back to mean


def test_weighted_median_simple() -> None:
    v = np.array([1.0, 2.0, 3.0, 4.0])
    w = np.array([1.0, 1.0, 1.0, 1.0])
    assert weighted_median(v, w) == 2.0  # ties resolved to lower

    # Heavy weight on a single value should win.
    w2 = np.array([0.1, 0.1, 100.0, 0.1])
    assert weighted_median(v, w2) == 3.0


def test_weighted_median_empty() -> None:
    assert np.isnan(weighted_median(np.array([]), np.array([])))


def test_estimate_to_dict() -> None:
    e = Estimate(value=1.0, ci_lo=0.5, ci_hi=1.5, n=10)
    d = e.to_dict()
    assert d == {"value": 1.0, "ci_lo": 0.5, "ci_hi": 1.5, "n": 10}

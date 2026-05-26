"""Wet vs dry pace decomposition.

A session is classified as "wet" if FastF1's weather data shows any
rainfall during the session AND any driver was on INTERMEDIATE or WET
compound for at least 5 laps during that session.

For each driver, we compute the median teammate-adjusted race-pace delta
in wet sessions and in dry sessions separately. The published metric is
the **difference of differences**: (wet_delta − dry_delta). Positive means
the driver gains time vs their teammate when conditions are wet, beyond
their dry baseline.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from pacelab import data
from pacelab.metrics.stats import Estimate, bootstrap_median_ci


def wet_session_keys(seasons: list[int]) -> set[str]:
    """Identify session keys that should be classified as wet."""
    weather = data.weather(seasons).collect()
    laps = data.laps(seasons).collect()
    sessions = data.sessions(seasons).select(["session_key", "session_type"]).collect()

    if weather.is_empty() or laps.is_empty():
        return set()

    # Race sessions only — qualifying wet is a different beast.
    race_keys = sessions.filter(pl.col("session_type") == "R").select("session_key")
    laps = laps.join(race_keys, on="session_key", how="inner")
    weather = weather.join(race_keys, on="session_key", how="inner")

    rain_keys = (
        weather.group_by("session_key")
        .agg(pl.col("rainfall").any().alias("any_rain"))
        .filter(pl.col("any_rain"))
        .select("session_key")
        .to_series().to_list()
    )

    wet_compound_keys = (
        laps.filter(pl.col("compound").is_in(["INTERMEDIATE", "WET"]))
        .group_by(["session_key", "driver_code"])
        .agg(pl.len().alias("n"))
        .filter(pl.col("n") >= 5)
        .select("session_key").unique()
        .to_series().to_list()
    )

    return set(rain_keys) & set(wet_compound_keys)


def driver_wet_vs_dry(
    fits: pl.DataFrame, driver_code: str, wet_keys: set[str]
) -> tuple[Estimate, Estimate, Estimate]:
    """Return (wet_pace_delta, dry_pace_delta, wet_minus_dry) estimates.

    All three are 95% bootstrap CIs on the median per-race pace delta
    (median across stint pairs in each race) restricted to the relevant
    subset of sessions.
    """
    rows = fits.filter(pl.col("driver_code") == driver_code)
    if rows.is_empty():
        empty = Estimate(value=float("nan"), ci_lo=float("nan"), ci_hi=float("nan"), n=0)
        return empty, empty, empty

    per_race = (
        rows.group_by("session_key")
        .agg(pl.col("pace_delta_s").median().alias("pace_delta_median"))
    )

    wet_vals = per_race.filter(pl.col("session_key").is_in(list(wet_keys)))["pace_delta_median"].to_numpy()
    dry_vals = per_race.filter(~pl.col("session_key").is_in(list(wet_keys)))["pace_delta_median"].to_numpy()
    wet_est = bootstrap_median_ci(wet_vals)
    dry_est = bootstrap_median_ci(dry_vals)
    # For the difference-of-differences we bootstrap the difference of the medians.
    if wet_est.n == 0 or dry_est.n == 0:
        diff = Estimate(value=float("nan"), ci_lo=float("nan"), ci_hi=float("nan"), n=0)
    else:
        rng = np.random.default_rng(0)
        n_resamples = 10_000
        wet_med = [
            float(np.median(rng.choice(wet_vals, size=len(wet_vals), replace=True)))
            for _ in range(n_resamples)
        ]
        dry_med = [
            float(np.median(rng.choice(dry_vals, size=len(dry_vals), replace=True)))
            for _ in range(n_resamples)
        ]
        diff_samples = np.asarray(wet_med) - np.asarray(dry_med)
        diff = Estimate(
            value=float(np.median(diff_samples)),
            ci_lo=float(np.quantile(diff_samples, 0.025)),
            ci_hi=float(np.quantile(diff_samples, 0.975)),
            n=min(wet_est.n, dry_est.n),
        )
    return wet_est, dry_est, diff


__all__ = ["wet_session_keys", "driver_wet_vs_dry"]

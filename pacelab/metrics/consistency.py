"""Stint consistency metric.

After de-trending a stint with `lap_time = α + β · stint_age + γ · lap_number`
(γ fixed at the fuel coefficient), the standard deviation of the residuals
is a robust measure of how metronomic the driver is. We then compute the
season-median per-stint SD, and a teammate delta on matched stint pairs.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from pacelab import data
from pacelab.config import METRICS
from pacelab.metrics.race_pace import matched_stint_pairs
from pacelab.metrics.stats import Estimate, bootstrap_median_ci, fit_linear_pace
from pacelab.metrics.validity import add_validity_flag


def _residual_sd_of_stint(stint_age: np.ndarray, fuel_corrected_s: np.ndarray) -> float:
    if len(stint_age) < 5:
        return float("nan")
    alpha, beta = fit_linear_pace(stint_age, fuel_corrected_s)
    pred = alpha + beta * stint_age
    resid = fuel_corrected_s - pred
    if len(resid) < 2:
        return float("nan")
    return float(np.std(resid, ddof=1))


def per_stint_consistency(seasons: list[int]) -> pl.DataFrame:
    """Return per-(session, driver, stint) residual SD after de-trending."""
    laps_l = add_validity_flag(data.laps(seasons))
    laps = laps_l.collect()
    if laps.is_empty():
        return pl.DataFrame()

    sessions = data.sessions(seasons).select(["session_key", "session_type"]).collect()
    race_keys = sessions.filter(pl.col("session_type") == "R").select("session_key")
    laps = laps.join(race_keys, on="session_key", how="inner")
    if laps.is_empty():
        return pl.DataFrame()

    clean = laps.filter(pl.col("clean_for_pace")).with_columns([
        (pl.col("lap_time_s") + METRICS.fuel_burn_seconds_per_lap * pl.col("lap_number")).alias(
            "fuel_corrected_s"
        ),
        pl.col("tyre_life").alias("stint_age"),
    ])

    rows: list[dict] = []
    for sk, dc, st, ages, fts, team in clean.select([
        "session_key", "driver_code", "stint", "team_name",
        pl.col("stint_age"),
        pl.col("fuel_corrected_s"),
    ]).group_by(["session_key", "driver_code", "stint"]).agg([
        pl.col("stint_age"),
        pl.col("fuel_corrected_s"),
        pl.col("team_name").first(),
    ]).select([
        "session_key", "driver_code", "stint",
        "stint_age", "fuel_corrected_s", "team_name",
    ]).iter_rows():
        sd = _residual_sd_of_stint(
            np.asarray(ages, dtype=float), np.asarray(fts, dtype=float),
        )
        rows.append({
            "session_key": sk,
            "driver_code": dc,
            "stint": st,
            "team_name": team,
            "n_laps": len(ages),
            "residual_sd_s": sd,
        })
    return pl.from_dicts(rows) if rows else pl.DataFrame()


def driver_consistency_estimate(consistency: pl.DataFrame, driver_code: str) -> Estimate:
    """Season-median per-stint residual SD for a driver, with bootstrap CI."""
    rows = consistency.filter(pl.col("driver_code") == driver_code)
    if rows.is_empty():
        return Estimate(value=float("nan"), ci_lo=float("nan"), ci_hi=float("nan"), n=0)
    return bootstrap_median_ci(np.asarray(rows["residual_sd_s"].to_list()))


def driver_consistency_vs_teammate(
    consistency: pl.DataFrame, fits_pairs: pl.DataFrame, driver_code: str
) -> Estimate:
    """For matched stint pairs, the median (driver_sd − teammate_sd)."""
    pairs = fits_pairs.filter(pl.col("driver_code") == driver_code)
    if pairs.is_empty():
        return Estimate(value=float("nan"), ci_lo=float("nan"), ci_hi=float("nan"), n=0)
    # Join consistency in for both sides.
    consist_a = consistency.select([
        "session_key",
        pl.col("driver_code").alias("driver_code"),
        pl.col("stint").alias("stint_a"),
        pl.col("residual_sd_s").alias("sd_driver"),
    ])
    consist_b = consistency.select([
        "session_key",
        pl.col("driver_code").alias("teammate_code"),
        pl.col("stint").alias("stint_b"),
        pl.col("residual_sd_s").alias("sd_teammate"),
    ])
    joined = (
        pairs.join(consist_a, on=["session_key", "driver_code", "stint_a"], how="inner")
             .join(consist_b, on=["session_key", "teammate_code", "stint_b"], how="inner")
             .filter(pl.col("sd_driver").is_finite() & pl.col("sd_teammate").is_finite())
    )
    deltas = (joined["sd_driver"] - joined["sd_teammate"]).to_numpy()
    return bootstrap_median_ci(deltas)


__all__ = [
    "per_stint_consistency",
    "driver_consistency_estimate",
    "driver_consistency_vs_teammate",
]

"""Qualifying-pace metric.

For each Grand Prix, identify each driver's fastest representative
qualifying lap and compare to their teammate's fastest lap *in the same
segment*. Report the season median delta with a bootstrap 95% CI.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from pacelab import data
from pacelab.metrics.stats import Estimate, bootstrap_median_ci
from pacelab.metrics.teammate import teammate_pairs


def per_session_qualifying_deltas(seasons: list[int]) -> pl.DataFrame:
    """For each qualifying session, return per-driver teammate delta in seconds."""
    results = data.results(seasons).collect()
    if results.is_empty():
        return pl.DataFrame()

    # Only keep qualifying sessions (session_type Q or SQ).
    sessions = data.sessions(seasons).select(["session_key", "session_type", "year", "round"]).collect()
    qual_keys = sessions.filter(pl.col("session_type").is_in(["Q", "SQ"])).select("session_key")
    res = results.join(qual_keys, on="session_key", how="inner")
    if res.is_empty():
        return pl.DataFrame()

    # The best lap in the highest segment the driver reached.
    res = res.with_columns([
        pl.when(pl.col("q3_time_s").is_finite()).then(pl.col("q3_time_s"))
          .when(pl.col("q2_time_s").is_finite()).then(pl.col("q2_time_s"))
          .otherwise(pl.col("q1_time_s")).alias("best_time_s"),
        pl.when(pl.col("q3_time_s").is_finite()).then(pl.lit(3))
          .when(pl.col("q2_time_s").is_finite()).then(pl.lit(2))
          .when(pl.col("q1_time_s").is_finite()).then(pl.lit(1))
          .otherwise(pl.lit(0)).alias("best_segment"),
    ])

    pairs = teammate_pairs(seasons)
    if pairs.is_empty():
        return pl.DataFrame()

    joined = pairs.join(
        res.select(["session_key", "driver_code", "best_time_s", "best_segment", "team_name"]),
        on=["session_key", "driver_code", "team_name"], how="inner"
    ).join(
        res.select([
            "session_key",
            pl.col("driver_code").alias("teammate_code"),
            pl.col("best_time_s").alias("teammate_best_s"),
            pl.col("best_segment").alias("teammate_segment"),
        ]),
        on=["session_key", "teammate_code"], how="inner"
    )

    # Compare only when both reached the same minimum segment.
    joined = joined.filter(
        (pl.col("best_segment") > 0)
        & (pl.col("teammate_segment") > 0)
        & (pl.col("best_time_s").is_finite())
        & (pl.col("teammate_best_s").is_finite())
    ).with_columns(
        (pl.col("best_time_s") - pl.col("teammate_best_s")).alias("delta_s"),
        pl.min_horizontal("best_segment", "teammate_segment").alias("compared_segment"),
    )
    return joined.select([
        "session_key", "driver_code", "teammate_code", "team_name",
        "best_time_s", "teammate_best_s", "delta_s", "compared_segment",
    ])


def driver_qualifying_estimate(deltas: pl.DataFrame, driver_code: str) -> Estimate:
    """Bootstrap CI on the median teammate-adjusted qualifying delta for one driver."""
    rows = deltas.filter(pl.col("driver_code") == driver_code)
    if rows.is_empty():
        return Estimate(value=float("nan"), ci_lo=float("nan"), ci_hi=float("nan"), n=0)
    return bootstrap_median_ci(np.asarray(rows["delta_s"].to_list()))


__all__ = [
    "per_session_qualifying_deltas",
    "driver_qualifying_estimate",
]

"""Race-day result metrics: recovery, error events, finishing-position delta."""

from __future__ import annotations

import numpy as np
import polars as pl

from pacelab import data
from pacelab.metrics.stats import Estimate, bootstrap_mean_ci


def race_recovery(seasons: list[int]) -> pl.DataFrame:
    """Per-race (grid_position − finish_position) for each driver.

    DNFs are flagged in `dnf` and contribute their last classified position
    minus the grid position (a negative number representing positions lost
    by retiring). Sprint races are excluded; only main races count.
    """
    sessions = data.sessions(seasons).select(["session_key", "session_type", "year", "round"]).collect()
    race_keys = sessions.filter(pl.col("session_type") == "R")
    results = data.results(seasons).collect()
    if results.is_empty() or race_keys.is_empty():
        return pl.DataFrame()

    res = results.join(race_keys, on="session_key", how="inner")
    res = res.with_columns([
        pl.col("classified_position").str.to_uppercase().is_in(
            ["DNF", "DNS", "DSQ", "NC", "R", "D", "W", "E", "F"]
        ).alias("dnf"),
    ])
    # When DNF, finish_position is set to last classified slot (FastF1 already does this).
    return res.select([
        "session_key", "year", "round", "driver_code", "team_name",
        "grid_position", "finish_position", "classified_position", "dnf",
        (pl.col("grid_position") - pl.col("finish_position")).alias("positions_gained"),
    ])


def driver_recovery_estimate(recovery: pl.DataFrame, driver_code: str) -> Estimate:
    """Average positions gained per race, with bootstrap CI."""
    rows = recovery.filter(pl.col("driver_code") == driver_code)
    if rows.is_empty():
        return Estimate(value=float("nan"), ci_lo=float("nan"), ci_hi=float("nan"), n=0)
    return bootstrap_mean_ci(np.asarray(rows["positions_gained"].to_list()))


def driver_dnf_rate(recovery: pl.DataFrame, driver_code: str) -> tuple[int, int]:
    rows = recovery.filter(pl.col("driver_code") == driver_code)
    if rows.is_empty():
        return (0, 0)
    return (int(rows.filter(pl.col("dnf")).height), int(rows.height))


__all__ = [
    "race_recovery",
    "driver_recovery_estimate",
    "driver_dnf_rate",
]

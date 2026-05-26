"""Race-pace and tyre-degradation metrics.

For each race stint shared with a teammate on the same compound, we fit
`lap_time = α + β · stint_age + γ · fuel_burn(lap)` with γ fixed at the
fleet-average fuel-burn coefficient. Two summary statistics are exported:

* **Race pace** — α difference between driver and teammate, weighted by
  the number of clean overlapping laps in the stint. Reported as a season
  median across stints, and a season median across races (i.e. median of
  per-race stint deltas).
* **Tyre degradation** — β value (s/lap) per compound per stint, reported
  as a driver-level weighted median with a teammate delta on the same
  stint pairs.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from pacelab import data
from pacelab.config import METRICS
from pacelab.metrics.stats import Estimate, bootstrap_median_ci, fit_linear_pace, weighted_median
from pacelab.metrics.teammate import teammate_pairs
from pacelab.metrics.validity import add_validity_flag


def matched_stint_pairs(seasons: list[int]) -> pl.DataFrame:
    """Identify (race, driver, teammate, compound, stint_a, stint_b) pairs.

    A pair is included only when both stints share the same compound and have
    at least METRICS.min_overlap_laps (default 5) clean overlapping laps where
    "overlapping" means the lap-number window intersects.
    """
    laps_l = add_validity_flag(data.laps(seasons))
    laps = laps_l.collect()
    if laps.is_empty():
        return pl.DataFrame()

    # Race sessions only.
    sessions = data.sessions(seasons).select(["session_key", "session_type"]).collect()
    race_keys = sessions.filter(pl.col("session_type") == "R").select("session_key")
    laps = laps.join(race_keys, on="session_key", how="inner")
    if laps.is_empty():
        return pl.DataFrame()

    pairs = teammate_pairs(seasons)
    if pairs.is_empty():
        return pl.DataFrame()

    pairs = pairs.join(race_keys, on="session_key", how="inner")

    # Restrict to clean-for-pace laps and apply fuel correction up-front.
    clean = laps.filter(pl.col("clean_for_pace")).with_columns(
        (pl.col("lap_time_s") + METRICS.fuel_burn_seconds_per_lap * pl.col("lap_number")).alias(
            "fuel_corrected_s"
        )
    )

    # Self-join to bring the teammate's clean laps next to the driver's.
    join = (
        pairs
        .join(clean.select([
            "session_key", "driver_code", "team_name", "stint", "compound", "lap_number",
            "fuel_corrected_s",
        ]), on=["session_key", "driver_code", "team_name"], how="inner")
        .rename({
            "stint": "stint_a",
            "compound": "compound_a",
            "lap_number": "lap_a",
            "fuel_corrected_s": "ft_a",
        })
        .join(
            clean.select([
                "session_key",
                pl.col("driver_code").alias("teammate_code"),
                pl.col("stint").alias("stint_b"),
                pl.col("compound").alias("compound_b"),
                pl.col("lap_number").alias("lap_b"),
                pl.col("fuel_corrected_s").alias("ft_b"),
            ]),
            on=["session_key", "teammate_code"], how="inner"
        )
        .filter(
            (pl.col("compound_a") == pl.col("compound_b"))
            & (pl.col("lap_a") == pl.col("lap_b"))
        )
    )

    # Group: per (session, driver, teammate, compound, stint_a, stint_b) — count overlap laps.
    grouped = join.group_by([
        "session_key", "driver_code", "teammate_code", "team_name",
        "stint_a", "stint_b", "compound_a",
    ]).agg([
        pl.len().alias("n_overlap_laps"),
        pl.col("lap_a").min().alias("first_lap"),
        pl.col("lap_a").max().alias("last_lap"),
    ])

    return grouped.filter(pl.col("n_overlap_laps") >= 5).rename({"compound_a": "compound"})


def stint_pair_fits(seasons: list[int]) -> pl.DataFrame:
    """For each matched stint pair, fit pace + degradation for both drivers.

    Returns one row per stint pair with α/β for driver and teammate plus the
    derived (pace delta, deg delta).
    """
    laps_l = add_validity_flag(data.laps(seasons))
    laps = laps_l.collect()
    pairs = matched_stint_pairs(seasons)
    if laps.is_empty() or pairs.is_empty():
        return pl.DataFrame()

    # Pre-compute fuel-corrected lap times.
    clean = laps.filter(pl.col("clean_for_pace")).with_columns([
        (pl.col("lap_time_s") + METRICS.fuel_burn_seconds_per_lap * pl.col("lap_number")).alias(
            "fuel_corrected_s"
        ),
        (pl.col("tyre_life")).alias("stint_age"),
    ])

    # Build a (session, driver, stint) -> {stint_age[], ft[]} lookup once.
    lookup: dict[tuple[str, str, int], tuple[np.ndarray, np.ndarray]] = {}
    for sk, dc, st, ages, fts in clean.select([
        "session_key", "driver_code", "stint",
        pl.col("stint_age"),
        pl.col("fuel_corrected_s"),
    ]).group_by(["session_key", "driver_code", "stint"]).agg([
        pl.col("stint_age"),
        pl.col("fuel_corrected_s"),
    ]).iter_rows():
        lookup[(sk, dc, int(st))] = (
            np.asarray(ages, dtype=float),
            np.asarray(fts, dtype=float),
        )

    out_rows: list[dict] = []
    for row in pairs.iter_rows(named=True):
        key_a = (row["session_key"], row["driver_code"], int(row["stint_a"]))
        key_b = (row["session_key"], row["teammate_code"], int(row["stint_b"]))
        if key_a not in lookup or key_b not in lookup:
            continue
        x_a, y_a = lookup[key_a]
        x_b, y_b = lookup[key_b]
        if len(y_a) < 5 or len(y_b) < 5:
            continue
        alpha_a, beta_a = fit_linear_pace(x_a, y_a)
        alpha_b, beta_b = fit_linear_pace(x_b, y_b)
        out_rows.append({
            "session_key": row["session_key"],
            "driver_code": row["driver_code"],
            "teammate_code": row["teammate_code"],
            "team_name": row["team_name"],
            "compound": row["compound"],
            "stint_a": row["stint_a"],
            "stint_b": row["stint_b"],
            "n_overlap_laps": row["n_overlap_laps"],
            "alpha_driver": alpha_a,
            "beta_driver": beta_a,
            "alpha_teammate": alpha_b,
            "beta_teammate": beta_b,
            "pace_delta_s": alpha_a - alpha_b,
            "deg_delta_s_per_lap": beta_a - beta_b,
        })
    if not out_rows:
        return pl.DataFrame()
    return pl.from_dicts(out_rows)


def driver_race_pace_estimate(fits: pl.DataFrame, driver_code: str) -> Estimate:
    """Median per-race pace delta (across stints, weighted by overlap laps),
    bootstrapped across races.
    """
    rows = fits.filter(pl.col("driver_code") == driver_code)
    if rows.is_empty():
        return Estimate(value=float("nan"), ci_lo=float("nan"), ci_hi=float("nan"), n=0)
    # Per-race aggregation: weighted median of per-stint pace deltas.
    per_race = rows.group_by("session_key").agg([
        pl.col("pace_delta_s"),
        pl.col("n_overlap_laps"),
    ])
    per_race_vals: list[float] = []
    for sk, deltas, weights in per_race.iter_rows():
        per_race_vals.append(
            weighted_median(np.asarray(deltas, dtype=float), np.asarray(weights, dtype=float))
        )
    return bootstrap_median_ci(np.asarray(per_race_vals))


def driver_degradation_estimate(
    fits: pl.DataFrame, driver_code: str, compound: str | None = None
) -> dict[str, Estimate]:
    """Per-compound (or overall) tyre-degradation deltas vs teammate.

    Returns a dict keyed by compound (or 'ALL'); each value is a bootstrap-CI
    estimate of the median per-stint β delta (s/lap).
    """
    rows = fits.filter(pl.col("driver_code") == driver_code)
    out: dict[str, Estimate] = {}
    if rows.is_empty():
        return out
    compounds = (
        [compound] if compound else
        sorted(rows.select("compound").unique().to_series().to_list())
    )
    for c in compounds:
        sub = rows.filter(pl.col("compound") == c)
        if sub.is_empty():
            continue
        out[c] = bootstrap_median_ci(np.asarray(sub["deg_delta_s_per_lap"].to_list()))
    return out


__all__ = [
    "matched_stint_pairs",
    "stint_pair_fits",
    "driver_race_pace_estimate",
    "driver_degradation_estimate",
]

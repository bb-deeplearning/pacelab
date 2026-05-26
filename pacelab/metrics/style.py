"""Telemetry-level driving-style fingerprints.

These metrics characterise *how* a driver drives, independent of *how
fast*. They consume per-lap telemetry sampled at FastF1's native rate
(~3.7 Hz position; higher for car data when transmitted by F1).

Status: phase-2, opt-in. Computed only for (year, round, session) where
the corresponding telemetry partitions exist.

Metrics implemented:

* **Throttle smoothness** — RMS of throttle derivative within
  corner-exit zones. Lower = smoother. Style fingerprint, not speed.
* **Braking signature** — average time on full brake per braking event
  (a proxy for "trail-brake vs threshold-brake" style). Higher = stays
  on the brakes deeper into the corner.
* **Full-throttle fraction** — share of the lap spent at ≥ 99% throttle.
  Tracks circuit character more than driver, but the *delta* vs teammate
  is informative ("this driver is hesitant on the same car").

Per-lap rather than per-session aggregation, then summarised across
clean racing laps. The teammate delta is the headline number.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import polars as pl

from pacelab.config import PARQUET_DIR
from pacelab.metrics.stats import Estimate, bootstrap_median_ci

log = logging.getLogger("pacelab.metrics.style")


def telemetry_paths(seasons: list[int]) -> list[Path]:
    paths: list[Path] = []
    for season in seasons:
        for p in sorted(PARQUET_DIR.glob(f"year={season}/round=*/session=R/telemetry_*.parquet")):
            paths.append(p)
    return paths


def per_lap_style_features(seasons: list[int]) -> pl.DataFrame:
    """Compute per-(driver, session, lap) style features from telemetry.

    Returns one row per lap with: throttle_rms, mean_brake_dwell_s,
    full_throttle_fraction, n_samples. Laps with < 200 samples (very short
    or partial) are dropped.
    """
    paths = telemetry_paths(seasons)
    if not paths:
        return pl.DataFrame()

    rows: list[dict] = []
    for path in paths:
        # session_key is encoded in the parent path: year=YYYY/round=NN/session=X
        parts = path.parts
        try:
            year = int([p for p in parts if p.startswith("year=")][0].split("=")[1])
            rnd = int([p for p in parts if p.startswith("round=")][0].split("=")[1])
            stype = [p for p in parts if p.startswith("session=")][0].split("=")[1]
        except (IndexError, ValueError):
            continue
        session_key = f"{year}-{rnd:02d}-{stype}"
        driver_code = path.stem.replace("telemetry_", "")

        try:
            df = pl.read_parquet(path)
        except Exception as e:
            log.warning("could not read %s: %s", path, e)
            continue
        if df.is_empty():
            continue

        for lap_no, lap_df in df.partition_by("lap_number", as_dict=True).items():
            # polars 1.x returns tuples as keys when partition_by has a single
            # column; handle both shapes defensively.
            if isinstance(lap_no, tuple):
                lap_no = lap_no[0]
            lap_no_int = int(lap_no)
            n_samples = lap_df.height
            if n_samples < 200:
                continue

            throttle = lap_df["throttle_pct"].to_numpy()
            brake = lap_df["brake"].to_numpy()
            time_s = lap_df["time_in_lap_s"].to_numpy()

            # Drop nans (telemetry has occasional gaps).
            mask = np.isfinite(throttle) & np.isfinite(time_s) & (np.diff(time_s, prepend=time_s[0] - 0.1) >= 0)
            if mask.sum() < 200:
                continue
            throttle = throttle[mask]
            brake = brake[mask]
            time_s = time_s[mask]

            # Throttle derivative
            dt = np.diff(time_s)
            dt[dt <= 0] = np.nan
            dthrot = np.diff(throttle) / dt
            dthrot = dthrot[np.isfinite(dthrot)]
            if dthrot.size == 0:
                continue
            throttle_rms = float(np.sqrt(np.mean(dthrot ** 2)))

            # Mean brake-event duration
            brake_changes = np.diff(brake.astype(np.int8), prepend=0)
            starts = np.where(brake_changes == 1)[0]
            ends = np.where(brake_changes == -1)[0]
            # Pair starts with the next end after them.
            event_durations: list[float] = []
            for s in starts:
                e = ends[ends > s]
                if e.size == 0:
                    continue
                event_durations.append(float(time_s[e[0]] - time_s[s]))
            mean_brake_dwell = float(np.mean(event_durations)) if event_durations else 0.0

            # Full-throttle fraction
            full_throttle_fraction = float(np.mean(throttle >= 99.0))

            rows.append({
                "session_key": session_key,
                "driver_code": driver_code,
                "lap_number": lap_no_int,
                "throttle_rms_pct_per_s": throttle_rms,
                "mean_brake_dwell_s": mean_brake_dwell,
                "full_throttle_fraction": full_throttle_fraction,
                "n_samples": n_samples,
            })

    if not rows:
        return pl.DataFrame()
    return pl.from_dicts(rows)


def teammate_delta_per_session(features: pl.DataFrame, results_lazy: pl.LazyFrame) -> pl.DataFrame:
    """Compute per-session teammate-delta of each style feature.

    Joins on (session, driver, team) to find the matching teammate row in
    the same session, then subtracts.
    """
    if features.is_empty():
        return features
    res = results_lazy.select(["session_key", "driver_code", "team_name"]).collect()
    feat = features.join(res, on=["session_key", "driver_code"], how="left")

    # Per-session median by driver
    by_driver = (
        feat.group_by(["session_key", "driver_code", "team_name"])
        .agg([
            pl.col("throttle_rms_pct_per_s").median().alias("throttle_rms"),
            pl.col("mean_brake_dwell_s").median().alias("brake_dwell"),
            pl.col("full_throttle_fraction").median().alias("full_throttle"),
        ])
    )

    # Self-join on team to bring teammate values alongside
    other = by_driver.rename({
        "driver_code": "teammate_code",
        "throttle_rms": "tm_throttle_rms",
        "brake_dwell": "tm_brake_dwell",
        "full_throttle": "tm_full_throttle",
    })
    pairs = by_driver.join(other, on=["session_key", "team_name"], how="inner").filter(
        pl.col("driver_code") != pl.col("teammate_code")
    )

    return pairs.with_columns([
        (pl.col("throttle_rms") - pl.col("tm_throttle_rms")).alias("delta_throttle_rms"),
        (pl.col("brake_dwell") - pl.col("tm_brake_dwell")).alias("delta_brake_dwell"),
        (pl.col("full_throttle") - pl.col("tm_full_throttle")).alias("delta_full_throttle"),
    ])


def driver_style_estimates(
    pairs: pl.DataFrame, driver_code: str
) -> dict[str, Estimate]:
    """Bootstrap CIs on the three style deltas for one driver."""
    rows = pairs.filter(pl.col("driver_code") == driver_code)
    if rows.is_empty():
        return {}
    return {
        "throttle_smoothness_delta": bootstrap_median_ci(np.asarray(rows["delta_throttle_rms"].to_list())),
        "brake_dwell_delta_s": bootstrap_median_ci(np.asarray(rows["delta_brake_dwell"].to_list())),
        "full_throttle_fraction_delta": bootstrap_median_ci(np.asarray(rows["delta_full_throttle"].to_list())),
    }


__all__ = [
    "per_lap_style_features",
    "teammate_delta_per_session",
    "driver_style_estimates",
    "telemetry_paths",
]

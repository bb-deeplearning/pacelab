"""Track-type breakdown metrics.

For each driver, compute the median race-pace delta vs teammate restricted
to each circuit archetype (street / high-speed / technical / balanced).
This is the closest descriptive analogue to "is X a Monaco driver vs a
Monza driver" that public data supports without telemetry-level features.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from pacelab import data
from pacelab.circuits import ARCHETYPE_LABELS, classify
from pacelab.metrics.stats import Estimate, bootstrap_median_ci


def _attach_archetypes(fits: pl.DataFrame, seasons: list[int]) -> pl.DataFrame:
    sessions = data.sessions(seasons).select(["session_key", "event_name"]).collect()
    if sessions.is_empty() or "archetype" in fits.columns:
        return fits
    sessions = sessions.with_columns(
        pl.col("event_name").map_elements(classify, return_dtype=pl.Utf8).alias("archetype")
    )
    return fits.join(sessions, on="session_key", how="left")


def enriched_fits(fits: pl.DataFrame, seasons: list[int]) -> pl.DataFrame:
    """Public helper: attach archetype column to a fits frame once."""
    return _attach_archetypes(fits, seasons)


def driver_pace_by_archetype(
    fits: pl.DataFrame, seasons: list[int], driver_code: str
) -> dict[str, Estimate]:
    """Per-archetype bootstrap CI on median per-race pace delta.

    Accepts either a raw fits frame or one already enriched with the
    `archetype` column. Pre-enriching avoids re-loading the sessions
    Parquet for every driver.
    """
    if fits.is_empty():
        return {}
    enriched = _attach_archetypes(fits, seasons)
    rows = enriched.filter(pl.col("driver_code") == driver_code)
    if rows.is_empty():
        return {}

    per_race = (
        rows.group_by(["session_key", "archetype"])
        .agg(pl.col("pace_delta_s").median().alias("pace_delta_median"))
    )

    out: dict[str, Estimate] = {}
    for arch in ARCHETYPE_LABELS:
        subset = per_race.filter(pl.col("archetype") == arch)
        if subset.is_empty():
            continue
        vals = np.asarray(subset["pace_delta_median"].to_list())
        out[arch] = bootstrap_median_ci(vals)
    return out


__all__ = ["driver_pace_by_archetype", "enriched_fits"]

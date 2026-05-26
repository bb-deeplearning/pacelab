"""Teammate-paired analysis utilities.

Many pacelab metrics are anchored on the "teammate delta" — the per-session
gap between a driver and the *other car in the same garage*. This module
identifies teammate pairs from the ingested results table and provides the
plumbing every per-metric module needs.
"""

from __future__ import annotations

import polars as pl

from pacelab import data


def teammate_pairs(seasons: list[int]) -> pl.DataFrame:
    """Return a DataFrame of (session_key, driver_a, driver_b, team_name).

    Each session yields one row per ordered (driver, teammate) pair within a team,
    so for a normal 2-car team you get 2 rows per session (a→b and b→a). This makes
    downstream joins cleaner: every driver row has its teammate spelled out.

    Teams with > 2 cars (rare; in-season replacements, third drivers in practice)
    produce all ordered pairs.
    """
    results = data.results(seasons).select([
        "session_key", "driver_code", "team_name"
    ]).collect()

    if results.is_empty():
        return pl.DataFrame(schema={
            "session_key": pl.Utf8,
            "driver_code": pl.Utf8,
            "teammate_code": pl.Utf8,
            "team_name": pl.Utf8,
        })

    # Self-join on (session_key, team_name), drop self-pairs.
    pairs = results.join(
        results.rename({"driver_code": "teammate_code"}),
        on=["session_key", "team_name"],
        how="inner",
    ).filter(pl.col("driver_code") != pl.col("teammate_code"))

    return pairs.select(["session_key", "driver_code", "teammate_code", "team_name"]).unique()


__all__ = ["teammate_pairs"]

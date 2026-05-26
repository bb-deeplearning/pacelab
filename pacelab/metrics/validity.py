"""Lap-validity filter.

A "clean lap" for analytical purposes excludes:

* in-laps and out-laps (driver entering or leaving the pits this lap)
* the first racing lap of a stint (tyre warm-up; not representative)
* deleted laps (track-limit penalties, etc.)
* laps under any non-green track status (yellow, SC, VSC, red)
* laps where FastF1's IsAccurate flag is False (the library's own bullshit detector)
* laps with no recorded lap time

The filter returns a copy of the input LazyFrame with a boolean column
`is_valid_lap` added. Downstream metrics may add further per-metric filters
(for example, the wheel-to-wheel metric requires gap-to-leader data).
"""

from __future__ import annotations

import polars as pl


def add_validity_flag(laps: pl.LazyFrame) -> pl.LazyFrame:
    """Add `is_valid_lap` and `clean_for_pace` boolean columns."""
    return laps.with_columns([
        # Track status of "1" means clear/green; anything else is a flag period.
        pl.col("track_status").map_elements(_is_green, return_dtype=pl.Boolean).alias("_track_green"),
        # Tyre warm-up: the first lap on a fresh set is rarely representative.
        (pl.col("tyre_life") <= 1).alias("_warmup_lap"),
    ]).with_columns([
        # Universal validity — used by every per-lap metric.
        (
            pl.col("lap_time_s").is_finite()
            & ~pl.col("deleted")
            & ~pl.col("pit_in")
            & ~pl.col("pit_out")
            & pl.col("is_accurate")
            & pl.col("_track_green")
        ).alias("is_valid_lap"),
    ]).with_columns([
        # Stricter filter used for pace metrics: also drops warm-up laps.
        (pl.col("is_valid_lap") & ~pl.col("_warmup_lap")).alias("clean_for_pace"),
    ])


def _is_green(track_status: str | None) -> bool:
    """FastF1 track_status is a string of digits, one per sector.

    Codes: 1=green, 2=yellow, 4=SC, 5=red, 6=VSC, 7=VSC end.
    A lap is "green" only if every sector flag is "1".
    """
    if track_status is None or track_status == "":
        return True
    return all(c == "1" for c in track_status)


__all__ = ["add_validity_flag"]

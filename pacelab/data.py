"""Loader utilities for the Parquet data layer.

All metrics modules consume Polars LazyFrames produced here. The lazy
glob-load means we can compute over multiple seasons without materialising
the whole thing in memory.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import polars as pl

from pacelab.config import PARQUET_DIR


def _glob(table: str) -> list[Path]:
    return sorted(PARQUET_DIR.glob(f"year=*/round=*/session=*/{table}.parquet"))


def _glob_seasons(table: str, seasons: list[int]) -> list[Path]:
    paths: list[Path] = []
    for y in seasons:
        paths.extend(sorted(PARQUET_DIR.glob(f"year={y}/round=*/session=*/{table}.parquet")))
    return paths


def laps(seasons: list[int] | None = None) -> pl.LazyFrame:
    paths = _glob_seasons("laps", seasons) if seasons else _glob("laps")
    if not paths:
        return pl.LazyFrame()
    return pl.scan_parquet(paths)


def stints(seasons: list[int] | None = None) -> pl.LazyFrame:
    paths = _glob_seasons("stints", seasons) if seasons else _glob("stints")
    if not paths:
        return pl.LazyFrame()
    return pl.scan_parquet(paths)


def results(seasons: list[int] | None = None) -> pl.LazyFrame:
    paths = _glob_seasons("results", seasons) if seasons else _glob("results")
    if not paths:
        return pl.LazyFrame()
    return pl.scan_parquet(paths)


def sessions(seasons: list[int] | None = None) -> pl.LazyFrame:
    paths = _glob_seasons("session", seasons) if seasons else _glob("session")
    if not paths:
        return pl.LazyFrame()
    return pl.scan_parquet(paths)


def weather(seasons: list[int] | None = None) -> pl.LazyFrame:
    paths = _glob_seasons("weather", seasons) if seasons else _glob("weather")
    if not paths:
        return pl.LazyFrame()
    return pl.scan_parquet(paths)


def drivers(seasons: list[int] | None = None) -> pl.LazyFrame:
    paths = _glob_seasons("drivers", seasons) if seasons else _glob("drivers")
    if not paths:
        return pl.LazyFrame()
    return pl.scan_parquet(paths)


@lru_cache(maxsize=8)
def session_year_round(season_filter: tuple[int, ...] | None = None) -> pl.DataFrame:
    """Helper: produce (session_key, year, round, session_type, event_name, ...)."""
    seasons = list(season_filter) if season_filter else None
    return sessions(seasons).collect()

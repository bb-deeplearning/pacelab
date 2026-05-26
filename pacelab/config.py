"""Centralised configuration for pacelab.

All paths and runtime parameters live here so that downstream modules import
constants instead of computing paths inline. Override with environment variables
prefixed with PACELAB_ where indicated.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser().resolve() if raw else default


REPO_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = _env_path("PACELAB_DATA_DIR", REPO_ROOT / "data")
CACHE_DIR = _env_path("PACELAB_CACHE_DIR", DATA_DIR / "cache")
PARQUET_DIR = _env_path("PACELAB_PARQUET_DIR", DATA_DIR / "parquet")
DERIVED_DIR = _env_path("PACELAB_DERIVED_DIR", DATA_DIR / "derived")

for d in (DATA_DIR, CACHE_DIR, PARQUET_DIR, DERIVED_DIR):
    d.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class IngestConfig:
    """Tuning knobs for the FastF1 ingest layer."""

    # Inclusive year range. FastF1's archive starts at 2018 for most session types.
    earliest_year: int = 2018
    # The "live" year — fetched but treated as incomplete.
    latest_year: int = 2025
    # Session types we ingest. The strings match FastF1's identifiers.
    session_types: tuple[str, ...] = ("Q", "R", "S", "SQ")  # Qual, Race, Sprint, Sprint Qual
    # How many laps a stint must have to be considered usable for any per-stint metric.
    min_stint_laps: int = 5


@dataclass(frozen=True)
class MetricsConfig:
    """Tuning knobs for the metrics layer."""

    # Standard fuel-burn coefficient in seconds per lap. F1 rule-of-thumb (~0.030s/lap).
    fuel_burn_seconds_per_lap: float = 0.030
    # Bootstrap resamples for CIs.
    bootstrap_resamples: int = 10_000
    # The dirty-air gap threshold in seconds.
    dirty_air_threshold_s: float = 1.0
    # Lap-time spike threshold for "error event" classification (s above stint pace).
    lap_spike_threshold_s: float = 1.5


INGEST = IngestConfig()
METRICS = MetricsConfig()

# FastF1 setup
def configure_fastf1() -> None:
    """Point FastF1 at our cache directory. Safe to call multiple times."""
    import fastf1

    fastf1.Cache.enable_cache(str(CACHE_DIR))

"""Telemetry ingest — opt-in extension to the base ingest pipeline.

Telemetry is heavy: ~700 samples per lap × 60 laps × 20 drivers per race
= ~840k rows per race × 24 races × 8 seasons = ~160M rows total.

We persist telemetry as a separate Parquet partition per (year, round,
session_type, driver_code) so the loader can read just one driver at a
time. Columns kept:

* time within lap (seconds), distance (m)
* speed (km/h), throttle (%), brake (bool), gear (int), RPM
* DRS state
* X, Y position (m, in track coordinates)
* lap number (joined back from the laps table)

This module does not run as part of `ingest backfill` — it has its own
CLI command `pacelab ingest telemetry --year 2024 --round 1`.
"""

from __future__ import annotations

import logging
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import polars as pl

from pacelab.config import PARQUET_DIR, configure_fastf1
from pacelab.ingest import session_partition_dir

log = logging.getLogger("pacelab.ingest.telemetry")
warnings.filterwarnings("ignore", category=FutureWarning)


TELEMETRY_DIR = PARQUET_DIR  # we slot into the existing partition tree


def telemetry_partition_path(
    year: int, rnd: int, session_type: str, driver_code: str
) -> Path:
    base = session_partition_dir(year, rnd, session_type)
    base.mkdir(parents=True, exist_ok=True)
    return base / f"telemetry_{driver_code}.parquet"


def _td_seconds(s: pd.Series) -> pd.Series:
    return pd.to_timedelta(s, errors="coerce").dt.total_seconds()


def ingest_telemetry_session(
    year: int, rnd: int, session_type: str, drivers: list[str] | None = None
) -> int:
    """Pull car telemetry for every driver in a session and persist to Parquet.

    Returns the number of (driver, lap) telemetry frames written.
    """
    import fastf1

    configure_fastf1()
    log.info("loading telemetry for %d round %d %s", year, rnd, session_type)
    s = fastf1.get_session(year, rnd, session_type)
    s.load(laps=True, telemetry=True)

    laps_df = s.laps
    if laps_df is None or laps_df.empty:
        log.warning("no laps for %d-%d-%s", year, rnd, session_type)
        return 0

    if drivers is None:
        drivers = sorted(laps_df["Driver"].dropna().unique().tolist())

    n_written = 0
    for dc in drivers:
        out_path = telemetry_partition_path(year, rnd, session_type, dc)
        if out_path.exists():
            continue
        driver_laps = laps_df.pick_drivers(dc)
        if driver_laps.empty:
            continue

        per_lap_frames: list[pd.DataFrame] = []
        for _, lap in driver_laps.iterrows():
            try:
                t = lap.get_telemetry()
            except Exception as e:
                log.debug("telemetry skip %s lap %s: %s", dc, lap.LapNumber, e)
                continue
            if t is None or t.empty:
                continue
            f = pd.DataFrame({
                "driver_code": dc,
                "lap_number": int(lap.LapNumber),
                "compound": str(lap.Compound or "UNKNOWN"),
                "stint": int(lap.Stint or 0),
                "tyre_life": int(lap.TyreLife or 0),
                "time_in_lap_s": _td_seconds(t["Time"]),
                "session_time_s": _td_seconds(t["SessionTime"]),
                "distance_m": pd.to_numeric(t["Distance"], errors="coerce"),
                "speed_kph": pd.to_numeric(t["Speed"], errors="coerce"),
                "throttle_pct": pd.to_numeric(t["Throttle"], errors="coerce"),
                "brake": t["Brake"].fillna(False).astype(bool),
                "gear": pd.to_numeric(t["nGear"], errors="coerce").fillna(0).astype("int16"),
                "rpm": pd.to_numeric(t["RPM"], errors="coerce"),
                "drs": pd.to_numeric(t["DRS"], errors="coerce").fillna(0).astype("int8"),
                "x": pd.to_numeric(t["X"], errors="coerce"),
                "y": pd.to_numeric(t["Y"], errors="coerce"),
            })
            per_lap_frames.append(f)

        if not per_lap_frames:
            continue

        df = pd.concat(per_lap_frames, ignore_index=True)
        pl_df = pl.from_pandas(df)
        pl_df.write_parquet(out_path, compression="zstd", compression_level=3)
        n_written += len(per_lap_frames)
        log.info(
            "wrote %s telemetry: %d laps, %d samples -> %s",
            dc, len(per_lap_frames), len(df), out_path.name,
        )

    return n_written


@dataclass
class TelemetryIngestReport:
    sessions_attempted: int = 0
    sessions_succeeded: int = 0
    n_lap_frames: int = 0
    failed: list[tuple[str, str]] = None  # type: ignore
    elapsed_s: float = 0.0


def backfill_telemetry(
    year_from: int, year_to: int, session_types: tuple[str, ...] = ("R",),
) -> TelemetryIngestReport:
    """Pull telemetry for every already-ingested session in the year range.

    We only pull races by default (telemetry-heavy enough that the qualifying
    + sprint + sprint-qualifying multiplier is rarely worth it). Set
    session_types to expand.
    """
    configure_fastf1()
    report = TelemetryIngestReport(failed=[])
    t0 = time.time()

    for year_dir in sorted(PARQUET_DIR.glob("year=*")):
        year = int(year_dir.name.split("=")[1])
        if not (year_from <= year <= year_to):
            continue
        for round_dir in sorted(year_dir.glob("round=*")):
            rnd = int(round_dir.name.split("=")[1])
            for stype in session_types:
                session_dir = round_dir / f"session={stype}"
                if not (session_dir / "laps.parquet").exists():
                    continue
                key = f"{year}-{rnd:02d}-{stype}"
                report.sessions_attempted += 1
                try:
                    n = ingest_telemetry_session(year, rnd, stype)
                    if n > 0:
                        report.n_lap_frames += n
                        report.sessions_succeeded += 1
                except Exception as e:
                    log.exception("telemetry failed for %s", key)
                    report.failed.append((key, str(e)))

    report.elapsed_s = time.time() - t0
    return report


__all__ = [
    "ingest_telemetry_session",
    "backfill_telemetry",
    "telemetry_partition_path",
    "TelemetryIngestReport",
]

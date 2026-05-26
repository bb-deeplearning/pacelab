"""FastF1 → Parquet ingest pipeline.

Responsibilities:

* Iterate over (year, round, session_type) and download via FastF1.
* Normalise FastF1's pandas data into polars DataFrames matching the
  schemas in `pacelab.schema`.
* Persist as partitioned Parquet under PARQUET_DIR.
* Be resumable, idempotent, and loudly fail on schema drift.

The full backfill is heavy (≈100 sessions per year × multiple years × a
network round-trip per session). The pipeline therefore:

* Skips sessions whose Parquet partition already exists, unless --force.
* Catches exceptions per-session so that one bad event does not abort
  the whole run (logged + summarised at end).
"""

from __future__ import annotations

import logging
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import polars as pl

from pacelab import schema as sch
from pacelab.config import CACHE_DIR, INGEST, PARQUET_DIR, configure_fastf1

log = logging.getLogger("pacelab.ingest")

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)


# ─────────────────────────────────────────────────────────────────────────────
# Path layout
# ─────────────────────────────────────────────────────────────────────────────
def session_key(year: int, rnd: int, session_type: str) -> str:
    return f"{year}-{rnd:02d}-{session_type}"


def session_partition_dir(year: int, rnd: int, session_type: str) -> Path:
    return PARQUET_DIR / f"year={year}" / f"round={rnd:02d}" / f"session={session_type}"


def is_ingested(year: int, rnd: int, session_type: str) -> bool:
    p = session_partition_dir(year, rnd, session_type)
    # We treat presence of laps.parquet as the marker — it is always produced.
    return (p / "laps.parquet").exists()


# ─────────────────────────────────────────────────────────────────────────────
# Conversion helpers
# ─────────────────────────────────────────────────────────────────────────────
def _td_to_seconds(td) -> float | None:
    """Convert a pandas Timedelta to seconds, returning None for NaT."""
    if td is None:
        return None
    try:
        if hasattr(td, "total_seconds"):
            s = td.total_seconds()
            return None if (s != s) else float(s)  # NaN check
    except Exception:
        pass
    return None


def _safe_int(v) -> int | None:
    try:
        if v is None or (isinstance(v, float) and (v != v)):
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def _safe_str(v) -> str | None:
    if v is None:
        return None
    s = str(v)
    return None if s in {"nan", "None", "NaT", ""} else s


def _safe_bool(v) -> bool:
    if v is None or (isinstance(v, float) and (v != v)):
        return False
    return bool(v)


# ─────────────────────────────────────────────────────────────────────────────
# Schedule
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class PlannedSession:
    year: int
    round: int
    session_type: str   # 'Q' | 'R' | 'S' | 'SQ' | 'FP1' | ...
    event_name: str
    circuit_name: str
    country: str
    session_start_utc: datetime
    is_sprint_weekend: bool


_FASTF1_SESSION_KIND_MAP = {
    "Race": "R",
    "Qualifying": "Q",
    "Sprint": "S",
    "Sprint Qualifying": "SQ",
    "Sprint Shootout": "SQ",   # 2023 sprint qualifying was branded "Sprint Shootout"
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
}


def planned_sessions(year: int, wanted_types: tuple[str, ...]) -> list[PlannedSession]:
    import fastf1

    out: list[PlannedSession] = []
    sched = fastf1.get_event_schedule(year, include_testing=False)
    for _, row in sched.iterrows():
        rnd = int(row["RoundNumber"])
        if rnd == 0:
            continue
        event_name = str(row["EventName"])
        circuit = str(row["Location"])
        country = str(row["Country"])
        is_sprint = "sprint" in str(row.get("EventFormat", "")).lower()
        for idx in range(1, 6):
            kind = row.get(f"Session{idx}")
            start = row.get(f"Session{idx}DateUtc")
            if kind is None or str(kind) == "nan":
                continue
            session_type = _FASTF1_SESSION_KIND_MAP.get(str(kind))
            if session_type is None:
                continue
            if session_type not in wanted_types:
                continue
            try:
                start_dt = (
                    start.to_pydatetime().replace(tzinfo=timezone.utc)
                    if hasattr(start, "to_pydatetime")
                    else None
                )
            except Exception:
                start_dt = None
            out.append(
                PlannedSession(
                    year=year,
                    round=rnd,
                    session_type=session_type,
                    event_name=event_name,
                    circuit_name=circuit,
                    country=country,
                    session_start_utc=start_dt or datetime(year, 1, 1, tzinfo=timezone.utc),
                    is_sprint_weekend=is_sprint,
                )
            )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Per-session ingest
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class SessionFrames:
    sessions: pl.DataFrame
    drivers: pl.DataFrame
    laps: pl.DataFrame
    weather: pl.DataFrame
    results: pl.DataFrame
    stints: pl.DataFrame


# Pandas helpers -------------------------------------------------------------
def _to_seconds_series(s: pd.Series) -> pd.Series:
    """Convert a pandas Timedelta series to float seconds (NaT -> NaN)."""
    return pd.to_timedelta(s, errors="coerce").dt.total_seconds()


def _ensure_str(s: pd.Series, default: str = "") -> pd.Series:
    return s.fillna(default).astype(str).replace({"nan": default, "NaT": default, "None": default})


def _ensure_int(s: pd.Series, default: int = 0) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(default).astype("int64")


def _ensure_float(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype("float64")


def _ensure_bool(s: pd.Series) -> pd.Series:
    return s.fillna(False).astype(bool)


def _laps_to_polars(laps_pd: pd.DataFrame, key: str) -> pl.DataFrame:
    if laps_pd is None or laps_pd.empty:
        return sch.empty_df("laps")
    df = pd.DataFrame({
        "session_key": key,
        "driver_code": _ensure_str(laps_pd["Driver"]),
        "team_name": _ensure_str(laps_pd["Team"]),
        "lap_number": _ensure_int(laps_pd["LapNumber"]),
        "stint": _ensure_int(laps_pd["Stint"]),
        "compound": _ensure_str(laps_pd["Compound"], "UNKNOWN"),
        "tyre_life": _ensure_int(laps_pd["TyreLife"]),
        "fresh_tyre": _ensure_bool(laps_pd["FreshTyre"]),
        "lap_time_s": _to_seconds_series(laps_pd["LapTime"]),
        "sector1_s": _to_seconds_series(laps_pd["Sector1Time"]),
        "sector2_s": _to_seconds_series(laps_pd["Sector2Time"]),
        "sector3_s": _to_seconds_series(laps_pd["Sector3Time"]),
        "speed_i1": _ensure_float(laps_pd["SpeedI1"]),
        "speed_i2": _ensure_float(laps_pd["SpeedI2"]),
        "speed_fl": _ensure_float(laps_pd["SpeedFL"]),
        "speed_st": _ensure_float(laps_pd["SpeedST"]),
        "is_personal_best": _ensure_bool(laps_pd["IsPersonalBest"]),
        "pit_in": laps_pd["PitInTime"].notna(),
        "pit_out": laps_pd["PitOutTime"].notna(),
        "is_accurate": _ensure_bool(laps_pd["IsAccurate"]),
        "track_status": _ensure_str(laps_pd["TrackStatus"], ""),
        "deleted": _ensure_bool(laps_pd["Deleted"]),
        "position": _ensure_int(laps_pd["Position"]),
        "lap_start_time_s": _to_seconds_series(laps_pd["LapStartTime"]),
        "lap_start_date_utc": pd.to_datetime(laps_pd["LapStartDate"], errors="coerce"),
    })
    pl_df = pl.from_pandas(df)
    return pl_df.cast(
        {k: v for k, v in sch.LAPS_SCHEMA.items() if k in pl_df.columns}, strict=False
    ).select(list(sch.LAPS_SCHEMA.keys()))


def _drivers_to_polars(results_pd: pd.DataFrame, year: int) -> pl.DataFrame:
    if results_pd is None or results_pd.empty:
        return sch.empty_df("drivers")
    df = pd.DataFrame({
        "year": year,
        "driver_code": _ensure_str(results_pd["Abbreviation"]),
        "driver_number": _ensure_int(results_pd["DriverNumber"]),
        "full_name": _ensure_str(results_pd["FullName"]),
        "team_name": _ensure_str(results_pd["TeamName"]),
        "team_color": _ensure_str(results_pd["TeamColor"]),
        "country_code": _ensure_str(results_pd["CountryCode"]),
    }).drop_duplicates(subset=["year", "driver_code"])
    pl_df = pl.from_pandas(df)
    return pl_df.cast(
        {k: v for k, v in sch.DRIVERS_SCHEMA.items() if k in pl_df.columns}, strict=False
    ).select(list(sch.DRIVERS_SCHEMA.keys()))


def _weather_to_polars(weather_pd: pd.DataFrame | None, key: str) -> pl.DataFrame:
    if weather_pd is None or weather_pd.empty:
        return sch.empty_df("weather")
    df = pd.DataFrame({
        "session_key": key,
        "time_s": _to_seconds_series(weather_pd["Time"]),
        "air_temp_c": _ensure_float(weather_pd["AirTemp"]),
        "track_temp_c": _ensure_float(weather_pd["TrackTemp"]),
        "humidity_pct": _ensure_float(weather_pd["Humidity"]),
        "pressure_mbar": _ensure_float(weather_pd["Pressure"]),
        "rainfall": _ensure_bool(weather_pd["Rainfall"]),
        "wind_speed_ms": _ensure_float(weather_pd["WindSpeed"]),
        "wind_direction_deg": _ensure_int(weather_pd["WindDirection"]),
    })
    pl_df = pl.from_pandas(df)
    return pl_df.cast(
        {k: v for k, v in sch.WEATHER_SCHEMA.items() if k in pl_df.columns}, strict=False
    ).select(list(sch.WEATHER_SCHEMA.keys()))


def _results_to_polars(results_pd: pd.DataFrame, key: str) -> pl.DataFrame:
    if results_pd is None or results_pd.empty:
        return sch.empty_df("results")
    df = pd.DataFrame({
        "session_key": key,
        "driver_code": _ensure_str(results_pd["Abbreviation"]),
        "team_name": _ensure_str(results_pd["TeamName"]),
        "grid_position": _ensure_int(results_pd["GridPosition"]),
        "finish_position": _ensure_int(results_pd["Position"]),
        "classified_position": _ensure_str(results_pd["ClassifiedPosition"]),
        "status": _ensure_str(results_pd["Status"]),
        "points": _ensure_float(results_pd["Points"]).fillna(0.0),
        "fastest_lap_rank": 0,
        "q1_time_s": _to_seconds_series(results_pd["Q1"]),
        "q2_time_s": _to_seconds_series(results_pd["Q2"]),
        "q3_time_s": _to_seconds_series(results_pd["Q3"]),
    })
    pl_df = pl.from_pandas(df)
    return pl_df.cast(
        {k: v for k, v in sch.RESULTS_SCHEMA.items() if k in pl_df.columns}, strict=False
    ).select(list(sch.RESULTS_SCHEMA.keys()))


def _stints_from_laps(laps: pl.DataFrame) -> pl.DataFrame:
    """Derive stints table by grouping laps by (driver, stint)."""
    if laps.is_empty():
        return sch.empty_df("stints")
    # A "clean lap" is non-pit, non-out, non-in, valid LapTime, in/out of stints excluded.
    laps = laps.with_columns([
        ((~pl.col("pit_in"))
            & (~pl.col("pit_out"))
            & (~pl.col("deleted"))
            & (pl.col("lap_time_s").is_finite())
            & (pl.col("is_accurate"))
        ).alias("_clean")
    ])
    grouped = laps.group_by(["session_key", "driver_code", "team_name", "stint", "compound"]).agg([
        pl.col("lap_number").min().alias("start_lap"),
        pl.col("lap_number").max().alias("end_lap"),
        pl.col("lap_number").count().alias("n_laps"),
        pl.col("fresh_tyre").first().alias("fresh_tyre_start"),
        pl.col("_clean").sum().alias("n_clean_laps"),
    ])
    return grouped.cast(
        {k: v for k, v in sch.STINTS_SCHEMA.items() if k in grouped.columns}, strict=False
    ).select(list(sch.STINTS_SCHEMA.keys()))


def ingest_session(plan: PlannedSession) -> SessionFrames | None:
    """Download and convert a single session. Returns None on hard failure."""
    import fastf1

    try:
        from fastf1.req import RateLimitExceededError  # type: ignore
    except ImportError:  # pragma: no cover
        class RateLimitExceededError(Exception):  # type: ignore
            pass

    key = session_key(plan.year, plan.round, plan.session_type)
    try:
        s = fastf1.get_session(plan.year, plan.round, plan.session_type)
        s.load(laps=True, telemetry=False, weather=True, messages=False)
    except RateLimitExceededError as e:
        # Surface as a typed exception so the orchestrator can pause.
        raise
    except Exception as e:
        msg = str(e)
        if "500 calls/h" in msg or "rate" in msg.lower() and "limit" in msg.lower():
            # Treat as rate-limit too — FastF1 sometimes wraps the error string.
            raise RuntimeError(f"RATE_LIMIT: {msg}")
        log.warning("load failed for %s: %s", key, e)
        return None

    laps = _laps_to_polars(s.laps, key)
    drivers = _drivers_to_polars(s.results, plan.year)
    weather = _weather_to_polars(s.weather_data, key) if s.weather_data is not None else sch.empty_df("weather")
    results = _results_to_polars(s.results, key)
    stints = _stints_from_laps(laps)

    session_row = pl.DataFrame([{
        "year": plan.year,
        "round": plan.round,
        "session_type": plan.session_type,
        "session_key": key,
        "event_name": plan.event_name,
        "circuit_name": plan.circuit_name,
        "country": plan.country,
        "session_start_utc": plan.session_start_utc.replace(tzinfo=None),
        "is_sprint_weekend": plan.is_sprint_weekend,
        "ingested_at": datetime.now(timezone.utc).replace(tzinfo=None),
    }]).cast({k: v for k, v in sch.SESSIONS_SCHEMA.items()}, strict=False)

    return SessionFrames(
        sessions=session_row,
        drivers=drivers,
        laps=laps,
        weather=weather,
        results=results,
        stints=stints,
    )


def persist(plan: PlannedSession, frames: SessionFrames) -> None:
    out = session_partition_dir(plan.year, plan.round, plan.session_type)
    out.mkdir(parents=True, exist_ok=True)
    frames.sessions.write_parquet(out / "session.parquet")
    frames.drivers.write_parquet(out / "drivers.parquet")
    frames.laps.write_parquet(out / "laps.parquet")
    frames.weather.write_parquet(out / "weather.parquet")
    frames.results.write_parquet(out / "results.parquet")
    frames.stints.write_parquet(out / "stints.parquet")


# ─────────────────────────────────────────────────────────────────────────────
# Top-level driver
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class IngestReport:
    attempted: int = 0
    skipped: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)
    succeeded: int = 0
    elapsed_s: float = 0.0


def backfill(
    from_year: int,
    to_year: int,
    session_types: Iterable[str] | None = None,
    force: bool = False,
    pause_on_rate_limit_s: float | None = None,
) -> IngestReport:
    """Ingest all sessions in a year range, skipping completed ones unless forced.

    By default we abort the run as soon as the FastF1/Ergast 500-calls/hour
    rate-limit hits, because resuming after a 65-minute sleep is rarely what
    the operator wants. Pass `pause_on_rate_limit_s` to keep retrying.
    """
    configure_fastf1()
    session_types = tuple(session_types) if session_types else INGEST.session_types

    try:
        from fastf1.req import RateLimitExceededError  # type: ignore
    except ImportError:  # pragma: no cover
        class RateLimitExceededError(Exception):  # type: ignore
            pass

    t0 = time.time()
    report = IngestReport()
    aborted = False

    for year in range(from_year, to_year + 1):
        if aborted:
            break
        try:
            plans = planned_sessions(year, session_types)
        except Exception as e:
            log.error("could not load schedule for %s: %s", year, e)
            continue
        for plan in plans:
            key = session_key(plan.year, plan.round, plan.session_type)
            report.attempted += 1
            if not force and is_ingested(plan.year, plan.round, plan.session_type):
                report.skipped += 1
                continue
            log.info("ingesting %s — %s", key, plan.event_name)
            attempts = 0
            while True:
                attempts += 1
                try:
                    frames = ingest_session(plan)
                    if frames is None:
                        report.failed.append((key, "load returned None"))
                    else:
                        persist(plan, frames)
                        report.succeeded += 1
                    break
                except (RateLimitExceededError, RuntimeError) as e:
                    is_rate = (
                        isinstance(e, RateLimitExceededError)
                        or "RATE_LIMIT" in str(e)
                        or "500 calls/h" in str(e)
                    )
                    if is_rate:
                        if pause_on_rate_limit_s and attempts < 3:
                            log.warning(
                                "rate limit on %s; sleeping %d min (retry %d/3)",
                                key, int(pause_on_rate_limit_s / 60), attempts,
                            )
                            time.sleep(pause_on_rate_limit_s)
                            continue
                        log.error("hit FastF1 rate limit at %s; aborting run", key)
                        report.failed.append((key, "rate limit reached; aborting"))
                        aborted = True
                        break
                    log.exception("failed to ingest %s", key)
                    report.failed.append((key, str(e)))
                    break
                except Exception as e:
                    log.exception("failed to ingest %s", key)
                    report.failed.append((key, str(e)))
                    break
            if aborted:
                break

    report.elapsed_s = time.time() - t0
    return report


__all__ = [
    "PlannedSession",
    "SessionFrames",
    "IngestReport",
    "session_key",
    "session_partition_dir",
    "is_ingested",
    "planned_sessions",
    "ingest_session",
    "persist",
    "backfill",
]

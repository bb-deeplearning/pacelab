"""Canonical schema definitions for the Parquet data layer.

Every ingested file conforms to one of the schemas in this module. The
schema strings double as machine-readable contracts: if a column is missing
or the type drifts, downstream metrics fail loudly at load time.
"""

from __future__ import annotations

import polars as pl

# ─────────────────────────────────────────────────────────────────────────────
# sessions.parquet — one row per (year, round, session_type)
# ─────────────────────────────────────────────────────────────────────────────
SESSIONS_SCHEMA: dict[str, pl.DataType] = {
    "year": pl.Int32,
    "round": pl.Int32,
    "session_type": pl.Utf8,  # Q, R, S, SQ, FP1, ...
    "session_key": pl.Utf8,   # f"{year}-{round:02d}-{session_type}"
    "event_name": pl.Utf8,
    "circuit_name": pl.Utf8,
    "country": pl.Utf8,
    "session_start_utc": pl.Datetime("us"),
    "is_sprint_weekend": pl.Boolean,
    "ingested_at": pl.Datetime("us"),
}

# ─────────────────────────────────────────────────────────────────────────────
# drivers.parquet — one row per (year, driver_code)
# ─────────────────────────────────────────────────────────────────────────────
DRIVERS_SCHEMA: dict[str, pl.DataType] = {
    "year": pl.Int32,
    "driver_code": pl.Utf8,         # 3-letter abbreviation (VER, HAM, LEC, ...)
    "driver_number": pl.Int32,
    "full_name": pl.Utf8,
    "team_name": pl.Utf8,
    "team_color": pl.Utf8,          # hex without #
    "country_code": pl.Utf8,
}

# ─────────────────────────────────────────────────────────────────────────────
# laps.parquet — one row per (session_key, driver_code, lap_number)
# ─────────────────────────────────────────────────────────────────────────────
LAPS_SCHEMA: dict[str, pl.DataType] = {
    "session_key": pl.Utf8,
    "driver_code": pl.Utf8,
    "team_name": pl.Utf8,
    "lap_number": pl.Int32,
    "stint": pl.Int32,
    "compound": pl.Utf8,             # SOFT | MEDIUM | HARD | INTERMEDIATE | WET | UNKNOWN
    "tyre_life": pl.Int32,           # laps since the tyre was fitted
    "fresh_tyre": pl.Boolean,
    "lap_time_s": pl.Float64,        # NaN if no lap time recorded
    "sector1_s": pl.Float64,
    "sector2_s": pl.Float64,
    "sector3_s": pl.Float64,
    "speed_i1": pl.Float64,          # speedtrap mph/kph from FastF1
    "speed_i2": pl.Float64,
    "speed_fl": pl.Float64,
    "speed_st": pl.Float64,
    "is_personal_best": pl.Boolean,
    "pit_in": pl.Boolean,            # ended in pit
    "pit_out": pl.Boolean,           # started from pit
    "is_accurate": pl.Boolean,       # FastF1 internal accuracy flag
    "track_status": pl.Utf8,         # string of digits where each digit codes a sector flag
    "deleted": pl.Boolean,           # track-limit deletion or similar
    "position": pl.Int32,            # car position at end of lap
    "lap_start_time_s": pl.Float64,  # seconds from session start
    "lap_start_date_utc": pl.Datetime("us"),
}

# ─────────────────────────────────────────────────────────────────────────────
# weather.parquet — one row per (session_key, sample_index)
# ─────────────────────────────────────────────────────────────────────────────
WEATHER_SCHEMA: dict[str, pl.DataType] = {
    "session_key": pl.Utf8,
    "time_s": pl.Float64,            # seconds from session start
    "air_temp_c": pl.Float64,
    "track_temp_c": pl.Float64,
    "humidity_pct": pl.Float64,
    "pressure_mbar": pl.Float64,
    "rainfall": pl.Boolean,
    "wind_speed_ms": pl.Float64,
    "wind_direction_deg": pl.Int32,
}

# ─────────────────────────────────────────────────────────────────────────────
# results.parquet — one row per (session_key, driver_code)
# ─────────────────────────────────────────────────────────────────────────────
RESULTS_SCHEMA: dict[str, pl.DataType] = {
    "session_key": pl.Utf8,
    "driver_code": pl.Utf8,
    "team_name": pl.Utf8,
    "grid_position": pl.Int32,
    "finish_position": pl.Int32,
    "classified_position": pl.Utf8,  # "1", "2", "DNF", "DNS", "DSQ"
    "status": pl.Utf8,                # FastF1 status string
    "points": pl.Float64,
    "fastest_lap_rank": pl.Int32,
    "q1_time_s": pl.Float64,
    "q2_time_s": pl.Float64,
    "q3_time_s": pl.Float64,
}

# ─────────────────────────────────────────────────────────────────────────────
# stints.parquet — one row per (session_key, driver_code, stint)
# Derived from laps.parquet; emitted at ingest time for convenience.
# ─────────────────────────────────────────────────────────────────────────────
STINTS_SCHEMA: dict[str, pl.DataType] = {
    "session_key": pl.Utf8,
    "driver_code": pl.Utf8,
    "team_name": pl.Utf8,
    "stint": pl.Int32,
    "compound": pl.Utf8,
    "start_lap": pl.Int32,
    "end_lap": pl.Int32,
    "n_laps": pl.Int32,
    "fresh_tyre_start": pl.Boolean,
    "n_clean_laps": pl.Int32,
}

ALL_SCHEMAS: dict[str, dict[str, pl.DataType]] = {
    "sessions": SESSIONS_SCHEMA,
    "drivers": DRIVERS_SCHEMA,
    "laps": LAPS_SCHEMA,
    "weather": WEATHER_SCHEMA,
    "results": RESULTS_SCHEMA,
    "stints": STINTS_SCHEMA,
}


def empty_df(schema_name: str) -> pl.DataFrame:
    """Return an empty DataFrame conforming to a named schema."""
    schema = ALL_SCHEMAS[schema_name]
    return pl.DataFrame(schema={k: v for k, v in schema.items()})

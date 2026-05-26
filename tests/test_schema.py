"""Tests for the schema definitions — make sure empty frames materialise cleanly."""

from __future__ import annotations

import polars as pl

from pacelab import schema as sch


def test_empty_frames_for_all_schemas() -> None:
    for name in sch.ALL_SCHEMAS:
        df = sch.empty_df(name)
        assert isinstance(df, pl.DataFrame)
        assert df.height == 0
        # Column ordering and types must match the declared schema.
        for col, dtype in sch.ALL_SCHEMAS[name].items():
            assert col in df.columns
            assert df.schema[col] == dtype


def test_lap_schema_includes_required_columns() -> None:
    required = {
        "session_key", "driver_code", "lap_number", "stint", "compound",
        "lap_time_s", "tyre_life", "is_accurate", "pit_in", "pit_out",
        "deleted", "track_status",
    }
    assert required.issubset(set(sch.LAPS_SCHEMA.keys()))


def test_session_key_format_is_documented() -> None:
    # Sanity for downstream joins on session_key.
    assert sch.SESSIONS_SCHEMA["session_key"] == pl.Utf8
    assert sch.LAPS_SCHEMA["session_key"] == pl.Utf8

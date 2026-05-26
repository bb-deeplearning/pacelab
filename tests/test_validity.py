"""Tests for the lap-validity filter."""

from __future__ import annotations

import polars as pl

from pacelab.metrics.validity import _is_green, add_validity_flag


def _make_laps() -> pl.LazyFrame:
    return pl.LazyFrame({
        "session_key": ["s"] * 6,
        "driver_code": ["A"] * 6,
        "lap_number": list(range(1, 7)),
        "tyre_life": [1, 2, 3, 4, 5, 6],
        "lap_time_s": [90.0, 90.1, 90.2, 90.3, 90.4, 90.5],
        "deleted":     [False] * 6,
        "pit_in":      [False, False, False, False, False, True],
        "pit_out":     [True,  False, False, False, False, False],
        "is_accurate": [True,  True,  True,  True,  False, True],
        "track_status":["1",   "1",   "12",  "1",   "1",   "1"],
    })


def test_green_check() -> None:
    assert _is_green("1") is True
    assert _is_green("11") is True
    assert _is_green("") is True
    assert _is_green(None) is True
    assert _is_green("12") is False
    assert _is_green("145") is False


def test_validity_flag_excludes_pit_inout_deleted_inaccurate_flag() -> None:
    out = add_validity_flag(_make_laps()).collect()
    # lap 1: pit_out -> not valid
    # lap 2: valid
    # lap 3: yellow flag -> not valid
    # lap 4: valid
    # lap 5: inaccurate -> not valid
    # lap 6: pit_in -> not valid
    valid = out["is_valid_lap"].to_list()
    assert valid == [False, True, False, True, False, False]


def test_clean_for_pace_drops_warmup() -> None:
    out = add_validity_flag(_make_laps()).collect()
    # lap 1 valid would be False already from pit_out, but also warm-up.
    # lap 2 has tyre_life=2 so it's still "warm-up" with our <=1 threshold? no, <=1 means lap 1
    # Actually with tyre_life=1 it's the very first racing lap; we drop only when tyre_life<=1.
    # So lap 2 (tyre_life=2) is fine.
    clean = out["clean_for_pace"].to_list()
    assert clean == [False, True, False, True, False, False]

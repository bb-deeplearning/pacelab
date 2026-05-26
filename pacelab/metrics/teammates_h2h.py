"""Build per-season teammate-pair summary artefacts.

For each (season, team) where both drivers stayed at the same team
for the season, produce a head-to-head record:

* Qualifying H2H (driver A beat driver B in qualifying X out of Y times)
* Race finish H2H (when both classified)
* Lap-pace H2H (per-race median race pace)
* DNF counts

This is the simplest possible "scoreboard" and is what every paddock
reporter writes about every Sunday morning. We compute it from data.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import polars as pl

from pacelab import data
from pacelab.config import DERIVED_DIR
from pacelab.metrics.qualifying import per_session_qualifying_deltas
from pacelab.metrics.race_pace import stint_pair_fits

TEAMMATES_DIR = DERIVED_DIR / "teammates"
TEAMMATES_DIR.mkdir(parents=True, exist_ok=True)


def build_season_teammate_h2h(season: int) -> dict[str, Any]:
    qual = per_session_qualifying_deltas([season])
    fits = stint_pair_fits([season])
    results = data.results([season]).collect()
    sessions = data.sessions([season]).select(["session_key", "session_type", "round"]).collect()

    out: list[dict[str, Any]] = []

    if results.is_empty():
        return _save({}, season, out)

    race_keys = sessions.filter(pl.col("session_type") == "R").select("session_key")
    race_results = results.join(race_keys, on="session_key", how="inner")

    # Group by team and emit one entry per team-pair-of-drivers.
    by_team: dict[str, set[str]] = defaultdict(set)
    for sk, dc, team in results.select(["session_key", "driver_code", "team_name"]).iter_rows():
        by_team[team].add(dc)

    for team, drivers in by_team.items():
        if len(drivers) != 2:
            # Skip teams with in-season driver changes for now (3+ drivers entries).
            continue
        a, b = sorted(drivers)

        # Qualifying H2H — count wins per side from per-session deltas.
        qsub = qual.filter(
            (pl.col("team_name") == team)
            & pl.col("driver_code").is_in([a, b])
        )
        a_qual_wins = b_qual_wins = qual_compared = 0
        if not qsub.is_empty():
            # Count where a's delta < 0 (a beat b) and vice versa; both rows exist per session.
            a_rows = qsub.filter(pl.col("driver_code") == a)
            qual_compared = int(a_rows.height)
            a_qual_wins = int(a_rows.filter(pl.col("delta_s") < 0).height)
            b_qual_wins = int(a_rows.filter(pl.col("delta_s") > 0).height)

        # Race-pace H2H — per-race winner from stint fits.
        a_race_wins = b_race_wins = race_compared = 0
        if not fits.is_empty():
            fsub = (
                fits.filter(
                    (pl.col("team_name") == team)
                    & (pl.col("driver_code") == a)
                    & (pl.col("teammate_code") == b)
                )
                .group_by("session_key")
                .agg(pl.col("pace_delta_s").median().alias("delta"))
            )
            race_compared = int(fsub.height)
            a_race_wins = int(fsub.filter(pl.col("delta") < 0).height)
            b_race_wins = int(fsub.filter(pl.col("delta") > 0).height)

        # Finish H2H — per-race winner when both classified.
        ra = race_results.filter(pl.col("driver_code") == a).select([
            "session_key", pl.col("finish_position").alias("pos_a"),
            pl.col("classified_position").alias("class_a"),
        ])
        rb = race_results.filter(pl.col("driver_code") == b).select([
            "session_key", pl.col("finish_position").alias("pos_b"),
            pl.col("classified_position").alias("class_b"),
        ])
        joined = ra.join(rb, on="session_key", how="inner")
        cls = joined.filter(
            ~pl.col("class_a").str.to_uppercase().is_in(["DNF", "DNS", "DSQ", "NC", "R", "D", "W", "E", "F"])
            & ~pl.col("class_b").str.to_uppercase().is_in(["DNF", "DNS", "DSQ", "NC", "R", "D", "W", "E", "F"])
            & (pl.col("pos_a") > 0)
            & (pl.col("pos_b") > 0)
        )
        finish_compared = int(cls.height)
        a_finish_wins = int(cls.filter(pl.col("pos_a") < pl.col("pos_b")).height)
        b_finish_wins = int(cls.filter(pl.col("pos_b") < pl.col("pos_a")).height)

        a_dnfs = int(race_results.filter(
            (pl.col("driver_code") == a)
            & pl.col("classified_position").str.to_uppercase().is_in(["DNF", "DNS", "DSQ", "R", "D", "W", "E", "F"])
        ).height)
        b_dnfs = int(race_results.filter(
            (pl.col("driver_code") == b)
            & pl.col("classified_position").str.to_uppercase().is_in(["DNF", "DNS", "DSQ", "R", "D", "W", "E", "F"])
        ).height)

        out.append({
            "team_name": team,
            "driver_a": a,
            "driver_b": b,
            "qualifying": {
                "a_wins": a_qual_wins,
                "b_wins": b_qual_wins,
                "compared": qual_compared,
            },
            "race_pace": {
                "a_wins": a_race_wins,
                "b_wins": b_race_wins,
                "compared": race_compared,
            },
            "finish_position": {
                "a_wins": a_finish_wins,
                "b_wins": b_finish_wins,
                "compared": finish_compared,
            },
            "dnfs": {"a": a_dnfs, "b": b_dnfs},
        })

    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "season": season,
        "pairs": sorted(out, key=lambda r: r["team_name"]),
    }
    return _save(payload, season, out)


def _save(payload: dict[str, Any], season: int, pairs: list[dict[str, Any]]) -> dict[str, Any]:
    (TEAMMATES_DIR / f"{season}.json").write_text(json.dumps(payload, default=str))
    return payload


def build_all_teammates(seasons: list[int]) -> int:
    count = 0
    for s in seasons:
        build_season_teammate_h2h(s)
        count += 1
    return count


__all__ = [
    "build_season_teammate_h2h",
    "build_all_teammates",
    "TEAMMATES_DIR",
]

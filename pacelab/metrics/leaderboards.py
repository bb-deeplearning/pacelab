"""Season-summary metrics: cross-driver rankings on each headline metric.

This module produces a single JSON file per season that lists, for each
metric we care about, the ranking of all drivers in that season with the
estimate and CI. The web UI uses it for the home-page leaderboard view.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pacelab.config import DERIVED_DIR

LEADERBOARDS_DIR = DERIVED_DIR / "leaderboards"
LEADERBOARDS_DIR.mkdir(parents=True, exist_ok=True)


# Stable metric ids the UI knows about.
METRIC_FIELDS: list[tuple[str, str, str, bool]] = [
    # (id, label, lower_is_better, ...)
    ("qualifying_pace_vs_teammate_s", "Qualifying pace vs teammate", "headline_metrics", True),
    ("race_pace_vs_teammate_s", "Race pace vs teammate", "headline_metrics", True),
    ("stint_consistency_residual_sd_s", "Stint consistency", "headline_metrics", True),
    ("consistency_delta_vs_teammate_s", "Consistency Δ vs teammate", "headline_metrics", True),
    ("positions_gained_per_race", "Positions gained / race", "headline_metrics", False),
]


def _load_profile(season: int, code: str) -> dict[str, Any] | None:
    from pacelab.metrics import PROFILES_DIR
    p: Path = PROFILES_DIR / f"{season}_{code}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def build_season_leaderboard(season: int) -> dict[str, Any]:
    from pacelab.metrics import PROFILES_DIR

    drivers = sorted(p.stem.split("_", 1)[1] for p in PROFILES_DIR.glob(f"{season}_*.json"))
    leaderboards: dict[str, list[dict[str, Any]]] = {}

    for field_id, field_label, section, lower_is_better in METRIC_FIELDS:
        entries: list[dict[str, Any]] = []
        for dc in drivers:
            profile = _load_profile(season, dc)
            if profile is None:
                continue
            metric = profile.get(section, {}).get(field_id)
            if not metric:
                continue
            entries.append({
                "driver_code": dc,
                "full_name": profile["driver"]["full_name"],
                "team_name": profile["driver"]["team_name"],
                "team_color": profile["driver"]["team_color"],
                "value": metric.get("value"),
                "ci_lo": metric.get("ci_lo"),
                "ci_hi": metric.get("ci_hi"),
                "n": metric.get("n"),
            })

        # Sort: lower is better → ascending, but NaNs to the bottom.
        def sort_key(row: dict[str, Any]) -> tuple[int, float]:
            v = row.get("value")
            if v is None or not isinstance(v, (int, float)):
                return (1, 0.0)
            return (0, v if lower_is_better else -v)

        entries.sort(key=sort_key)
        leaderboards[field_id] = entries

    out = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "season": season,
        "leaderboards": leaderboards,
        "metrics": [
            {
                "id": field_id,
                "label": label,
                "section": section,
                "lower_is_better": lower_is_better,
            }
            for field_id, label, section, lower_is_better in METRIC_FIELDS
        ],
    }
    (LEADERBOARDS_DIR / f"{season}.json").write_text(json.dumps(out, default=str))
    return out


def build_all_leaderboards(seasons: list[int]) -> int:
    count = 0
    for s in seasons:
        build_season_leaderboard(s)
        count += 1
    return count


__all__ = [
    "build_season_leaderboard",
    "build_all_leaderboards",
    "LEADERBOARDS_DIR",
    "METRIC_FIELDS",
]

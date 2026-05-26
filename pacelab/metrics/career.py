"""All-time / career aggregations across seasons.

Pulls every (season, driver) profile JSON and produces:

* `careers.json` — per-driver-code, list of yearly metric snapshots
* `alltime.json` — leaderboards aggregated across all available seasons
  via inverse-variance-weighted averages of the per-season point estimates
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from pacelab.config import DERIVED_DIR

CAREERS_FILE = DERIVED_DIR / "careers.json"
ALLTIME_FILE = DERIVED_DIR / "alltime.json"


HEADLINE_METRICS: list[tuple[str, str, str, bool]] = [
    ("qualifying_pace_vs_teammate_s", "Qualifying pace vs teammate", "headline_metrics", True),
    ("race_pace_vs_teammate_s",       "Race pace vs teammate",      "headline_metrics", True),
    ("stint_consistency_residual_sd_s","Stint consistency",          "headline_metrics", True),
    ("consistency_delta_vs_teammate_s","Consistency Δ vs teammate",  "headline_metrics", True),
    ("positions_gained_per_race",     "Positions gained / race",     "headline_metrics", False),
]


def _profile_paths() -> list[tuple[int, str]]:
    from pacelab.metrics import PROFILES_DIR

    out: list[tuple[int, str]] = []
    for p in sorted(PROFILES_DIR.glob("*.json")):
        stem = p.stem  # like 2024_VER
        try:
            season_str, code = stem.split("_", 1)
            out.append((int(season_str), code))
        except ValueError:
            continue
    return out


def _load(season: int, code: str) -> dict[str, Any] | None:
    from pacelab.metrics import PROFILES_DIR
    p = PROFILES_DIR / f"{season}_{code}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def _ci_half_width(metric: dict[str, Any]) -> float | None:
    lo = metric.get("ci_lo")
    hi = metric.get("ci_hi")
    if lo is None or hi is None or not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)):
        return None
    if math.isnan(lo) or math.isnan(hi):
        return None
    return (hi - lo) / 2.0


def _ivw_combine(points: list[tuple[float, float, int]]) -> dict[str, Any]:
    """Inverse-variance-weighted combination of (value, ci_half, n) samples.

    Treats ci_half as a 1.96-sigma half-width, so sigma ≈ ci_half / 1.96.
    Returns aggregated value, approximate 95% CI, and total n. Falls back to
    simple mean if any CI is missing.
    """
    cleaned = [
        (v, ch, n) for (v, ch, n) in points
        if v is not None and not math.isnan(v) and (ch is not None and ch > 0)
    ]
    if not cleaned:
        # Try without CI: simple unweighted mean over available point estimates.
        fallback = [(v, 0.0, n) for (v, ch, n) in points if v is not None and not math.isnan(v)]
        if not fallback:
            return {"value": None, "ci_lo": None, "ci_hi": None, "n": 0, "seasons": 0}
        vals = [v for v, _, _ in fallback]
        ns = sum(n for _, _, n in fallback)
        m = sum(vals) / len(vals)
        return {"value": m, "ci_lo": m, "ci_hi": m, "n": ns, "seasons": len(fallback)}

    weights = [1.0 / (ch / 1.96) ** 2 for _, ch, _ in cleaned]
    wsum = sum(weights)
    pooled = sum(w * v for (v, _, _), w in zip(cleaned, weights)) / wsum
    pooled_se = math.sqrt(1.0 / wsum)
    ci_lo = pooled - 1.96 * pooled_se
    ci_hi = pooled + 1.96 * pooled_se
    return {
        "value": pooled,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "n": sum(n for _, _, n in cleaned),
        "seasons": len(cleaned),
    }


def build_careers() -> dict[str, Any]:
    by_code: dict[str, dict[str, Any]] = {}

    for (season, code) in _profile_paths():
        profile = _load(season, code)
        if profile is None:
            continue
        if code not in by_code:
            by_code[code] = {
                "driver_code": code,
                "full_name": profile["driver"]["full_name"],
                "country_code": profile["driver"]["country_code"],
                "seasons": [],
            }
        # Always keep the latest full_name (in case a driver's spelling changed).
        by_code[code]["full_name"] = profile["driver"]["full_name"]
        by_code[code]["country_code"] = profile["driver"]["country_code"]

        season_entry = {
            "season": season,
            "team_name": profile["driver"]["team_name"],
            "team_color": profile["driver"]["team_color"],
            "teammates": profile["driver"].get("teammates", []),
            "metrics": {},
        }
        for field_id, _label, section, _lower in HEADLINE_METRICS:
            m = profile.get(section, {}).get(field_id)
            if m:
                season_entry["metrics"][field_id] = {
                    "value": m.get("value"),
                    "ci_lo": m.get("ci_lo"),
                    "ci_hi": m.get("ci_hi"),
                    "n": m.get("n"),
                }
        season_entry["reliability"] = profile.get("reliability")
        by_code[code]["seasons"].append(season_entry)

    # Sort each driver's seasons chronologically.
    for v in by_code.values():
        v["seasons"].sort(key=lambda s: s["season"])

    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "drivers": sorted(by_code.values(), key=lambda d: d["full_name"]),
    }
    CAREERS_FILE.write_text(json.dumps(payload, default=str))
    return payload


def build_alltime() -> dict[str, Any]:
    careers = json.loads(CAREERS_FILE.read_text()) if CAREERS_FILE.exists() else build_careers()

    leaderboards: dict[str, list[dict[str, Any]]] = {}

    for field_id, label, _section, lower_is_better in HEADLINE_METRICS:
        rows: list[dict[str, Any]] = []
        for driver in careers["drivers"]:
            points: list[tuple[float, float, int]] = []
            seasons_covered: list[int] = []
            teams_covered: list[str] = []
            for s in driver["seasons"]:
                m = s["metrics"].get(field_id)
                if not m:
                    continue
                v = m.get("value")
                ch = _ci_half_width(m)
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    continue
                points.append((v, ch if ch is not None else 0.0, int(m.get("n") or 0)))
                seasons_covered.append(int(s["season"]))
                teams_covered.append(s["team_name"])

            if not points:
                continue
            ivw = _ivw_combine(points)
            if ivw["value"] is None:
                continue

            latest = driver["seasons"][-1]
            rows.append({
                "driver_code": driver["driver_code"],
                "full_name": driver["full_name"],
                "latest_team": latest["team_name"],
                "latest_team_color": latest["team_color"],
                "value": ivw["value"],
                "ci_lo": ivw["ci_lo"],
                "ci_hi": ivw["ci_hi"],
                "n": ivw["n"],
                "seasons_count": ivw["seasons"],
                "seasons": seasons_covered,
                "teams": sorted(set(teams_covered)),
            })

        rows.sort(key=lambda r: (
            0 if r["value"] is not None else 1,
            r["value"] if lower_is_better else -r["value"],
        ))
        leaderboards[field_id] = rows

    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "metrics": [
            {
                "id": fid,
                "label": label,
                "section": section,
                "lower_is_better": lower_is_better,
            }
            for fid, label, section, lower_is_better in HEADLINE_METRICS
        ],
        "leaderboards": leaderboards,
    }
    ALLTIME_FILE.write_text(json.dumps(payload, default=str))
    return payload


__all__ = [
    "build_careers",
    "build_alltime",
    "CAREERS_FILE",
    "ALLTIME_FILE",
]

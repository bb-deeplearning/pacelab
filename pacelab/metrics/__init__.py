"""Top-level metric orchestrator.

Produces per-driver profile JSON files under data/derived/profiles/.
Each file is a self-describing payload the API serves verbatim.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import polars as pl

from pacelab import data
from pacelab.circuits import ARCHETYPE_LABELS
from pacelab.config import DERIVED_DIR
from pacelab.metrics.consistency import (
    driver_consistency_estimate,
    driver_consistency_vs_teammate,
    per_stint_consistency,
)
from pacelab.metrics.qualifying import driver_qualifying_estimate, per_session_qualifying_deltas
from pacelab.metrics.race_pace import (
    driver_degradation_estimate,
    driver_race_pace_estimate,
    stint_pair_fits,
)
from pacelab.metrics.recovery import driver_dnf_rate, driver_recovery_estimate, race_recovery
from pacelab.metrics.stats import Estimate
from pacelab.metrics.track_type import driver_pace_by_archetype, enriched_fits
from pacelab.metrics.weather import driver_wet_vs_dry, wet_session_keys

log = logging.getLogger("pacelab.metrics")

PROFILES_DIR = DERIVED_DIR / "profiles"
PROFILES_DIR.mkdir(parents=True, exist_ok=True)

INDEX_FILE = DERIVED_DIR / "index.json"


def _estimate_dict(est: Estimate) -> dict[str, float | int]:
    return est.to_dict()


def _per_session_qual_rows(deltas: pl.DataFrame, driver_code: str) -> list[dict[str, Any]]:
    rows = deltas.filter(pl.col("driver_code") == driver_code).sort("session_key").to_dicts()
    return rows


def _per_race_pace_rows(fits: pl.DataFrame, driver_code: str) -> list[dict[str, Any]]:
    rows = (
        fits.filter(pl.col("driver_code") == driver_code)
            .group_by(["session_key", "teammate_code"])
            .agg([
                pl.col("pace_delta_s").median().alias("pace_delta_median"),
                pl.col("deg_delta_s_per_lap").median().alias("deg_delta_median"),
                pl.col("n_overlap_laps").sum().alias("n_overlap_laps"),
                pl.col("compound").n_unique().alias("n_compounds"),
            ])
            .sort("session_key")
            .to_dicts()
    )
    return rows


def _build_driver_profile(
    *,
    season: int,
    driver_code: str,
    full_name: str,
    team_name: str,
    team_color: str,
    country_code: str,
    qual_deltas: pl.DataFrame,
    fits: pl.DataFrame,
    consistency: pl.DataFrame,
    recovery: pl.DataFrame,
    wet_keys: set[str],
    sessions_df: pl.DataFrame,
) -> dict[str, Any]:

    qual_est = driver_qualifying_estimate(qual_deltas, driver_code)
    pace_est = driver_race_pace_estimate(fits, driver_code)
    deg_by_compound = driver_degradation_estimate(fits, driver_code)
    consistency_est = driver_consistency_estimate(consistency, driver_code)
    consistency_vs_tm = driver_consistency_vs_teammate(consistency, fits, driver_code)
    recovery_est = driver_recovery_estimate(recovery, driver_code)
    dnfs, races = driver_dnf_rate(recovery, driver_code)
    wet_est, dry_est, wet_minus_dry = driver_wet_vs_dry(fits, driver_code, wet_keys)
    by_archetype = driver_pace_by_archetype(fits, [season], driver_code)

    teammates_set: set[str] = set()
    teammates_set.update(qual_deltas.filter(pl.col("driver_code") == driver_code)["teammate_code"].to_list())
    teammates_set.update(fits.filter(pl.col("driver_code") == driver_code)["teammate_code"].to_list())

    # Last race result for the recency strip.
    rec = recovery.filter(pl.col("driver_code") == driver_code).sort("round")
    last = rec.tail(1).to_dicts()[0] if not rec.is_empty() else None
    points_by_race = rec.select(["session_key", "round", "finish_position"]).to_dicts()

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "driver": {
            "code": driver_code,
            "full_name": full_name,
            "team_name": team_name,
            "team_color": team_color,
            "country_code": country_code,
            "season": season,
            "teammates": sorted(teammates_set),
        },
        "headline_metrics": {
            "qualifying_pace_vs_teammate_s": {
                **_estimate_dict(qual_est),
                "definition": "Median per-session delta (driver_best_qual − teammate_best_qual) "
                              "across all qualifying sessions in the window where both drivers "
                              "reached the same Q-segment. 95% percentile bootstrap CI over sessions.",
                "lower_is_better": True,
            },
            "race_pace_vs_teammate_s": {
                **_estimate_dict(pace_est),
                "definition": "Per-race median of per-stint α(driver) − α(teammate), where α is "
                              "the intercept of lap_time = α + β·stint_age + γ·lap_number with γ "
                              "fixed at 0.030 s/lap (fuel coefficient). Stint pairs are matched on "
                              "session, compound, and overlapping lap windows of ≥ 5 clean laps. "
                              "95% percentile bootstrap CI over races.",
                "lower_is_better": True,
            },
            "stint_consistency_residual_sd_s": {
                **_estimate_dict(consistency_est),
                "definition": "Median per-stint standard deviation of lap-time residuals after "
                              "de-trending with α + β·stint_age + 0.030·lap_number. Lower = more "
                              "metronomic. 95% bootstrap CI over stints.",
                "lower_is_better": True,
            },
            "consistency_delta_vs_teammate_s": {
                **_estimate_dict(consistency_vs_tm),
                "definition": "Median (driver_stint_SD − teammate_stint_SD) on matched stint pairs. "
                              "Negative = more consistent than teammate.",
                "lower_is_better": True,
            },
            "positions_gained_per_race": {
                **_estimate_dict(recovery_est),
                "definition": "Mean of (grid_position − finish_position) across all main races "
                              "in the window. DNFs use the classified position at retirement.",
                "lower_is_better": False,
            },
        },
        "tyre_management": {
            "by_compound_deg_delta_s_per_lap": {
                compound: {
                    **_estimate_dict(est),
                    "definition": f"Median (driver_β − teammate_β) on matched {compound} stint "
                                  "pairs, where β is the fuel-corrected per-lap degradation slope.",
                    "lower_is_better": True,
                }
                for compound, est in deg_by_compound.items()
            },
        },
        "track_type": {
            "pace_vs_teammate_by_archetype_s": {
                arch: {
                    **_estimate_dict(est),
                    "label": ARCHETYPE_LABELS.get(arch, arch),
                    "definition": "Median per-race pace delta vs teammate at "
                                  f"{ARCHETYPE_LABELS.get(arch, arch).lower()} circuits this season. "
                                  "95% bootstrap CI over races.",
                    "lower_is_better": True,
                }
                for arch, est in by_archetype.items()
            },
        },
        "wet_vs_dry": {
            "wet_pace_vs_teammate_s": {
                **_estimate_dict(wet_est),
                "definition": "Median per-race pace delta in races classified as wet (any rainfall "
                              "AND ≥1 driver on INTERMEDIATE/WET for ≥5 laps). 95% bootstrap CI.",
                "lower_is_better": True,
            },
            "dry_pace_vs_teammate_s": {
                **_estimate_dict(dry_est),
                "definition": "Median per-race pace delta in dry races.",
                "lower_is_better": True,
            },
            "wet_minus_dry_s": {
                **_estimate_dict(wet_minus_dry),
                "definition": "Wet pace delta minus dry pace delta. Negative = the driver gains "
                              "time vs teammate when conditions become wet, beyond their dry baseline.",
                "lower_is_better": True,
            },
        },
        "reliability": {
            "dnfs": dnfs,
            "races_started": races,
            "dnf_rate": (dnfs / races) if races else 0.0,
        },
        "per_session": {
            "qualifying": _per_session_qual_rows(qual_deltas, driver_code),
            "race": _per_race_pace_rows(fits, driver_code),
            "race_results": rec.to_dicts(),
        },
        "last_race": last,
        "points_by_race": points_by_race,
    }


def build_all(seasons: list[int]) -> dict[str, Any]:
    """Compute and persist per-driver profiles for the given seasons.

    Profiles are written one-per-season-per-driver into data/derived/profiles/.
    An index.json is also written with metadata about which drivers exist.
    """
    t0 = time.time()
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    log.info("loading data...")
    drivers = data.drivers(seasons).collect()
    sessions_df = data.sessions(seasons).collect()
    if drivers.is_empty():
        log.warning("no drivers in ingested data — did you run `pacelab ingest backfill`?")
        return {"n_drivers": 0, "n_seasons": 0, "output_path": str(PROFILES_DIR), "elapsed_s": 0.0}

    by_season: dict[int, list[str]] = defaultdict(list)
    index_entries: list[dict[str, Any]] = []

    for season in sorted(set(seasons)):
        log.info("computing metrics for season %d...", season)
        season_list = [season]

        qual_deltas = per_session_qualifying_deltas(season_list)
        fits = stint_pair_fits(season_list)
        fits_enriched = enriched_fits(fits, season_list) if not fits.is_empty() else fits
        consistency = per_stint_consistency(season_list)
        recovery = race_recovery(season_list)
        wet_keys = wet_session_keys(season_list)
        season_drivers = (
            drivers.filter(pl.col("year") == season)
            .unique(subset=["driver_code"], keep="last")
        )

        for row in season_drivers.iter_rows(named=True):
            dc = row["driver_code"]
            if not dc:
                continue
            profile = _build_driver_profile(
                season=season,
                driver_code=dc,
                full_name=row["full_name"],
                team_name=row["team_name"],
                team_color=row["team_color"],
                country_code=row["country_code"],
                qual_deltas=qual_deltas if not qual_deltas.is_empty() else pl.DataFrame(
                    schema={
                        "session_key": pl.Utf8, "driver_code": pl.Utf8,
                        "teammate_code": pl.Utf8, "team_name": pl.Utf8,
                        "best_time_s": pl.Float64, "teammate_best_s": pl.Float64,
                        "delta_s": pl.Float64, "compared_segment": pl.Int32,
                    }
                ),
                fits=fits_enriched if not fits_enriched.is_empty() else pl.DataFrame(),
                consistency=consistency if not consistency.is_empty() else pl.DataFrame(),
                recovery=recovery if not recovery.is_empty() else pl.DataFrame(),
                wet_keys=wet_keys,
                sessions_df=sessions_df,
            )
            (PROFILES_DIR / f"{season}_{dc}.json").write_text(json.dumps(profile, indent=2, default=str))
            by_season[season].append(dc)
            index_entries.append({
                "season": season,
                "driver_code": dc,
                "full_name": row["full_name"],
                "team_name": row["team_name"],
                "team_color": row["team_color"],
                "country_code": row["country_code"],
            })

    INDEX_FILE.write_text(json.dumps({
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "seasons": sorted(by_season.keys()),
        "drivers": index_entries,
    }, indent=2, default=str))

    # Build per-season leaderboards from the freshly-written profiles.
    from pacelab.metrics.leaderboards import build_season_leaderboard
    for s in sorted(by_season.keys()):
        build_season_leaderboard(s)

    return {
        "n_drivers": len(index_entries),
        "n_seasons": len(by_season),
        "output_path": str(PROFILES_DIR),
        "elapsed_s": time.time() - t0,
    }


__all__ = ["build_all", "PROFILES_DIR", "INDEX_FILE"]

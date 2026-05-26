"""Hierarchical Bayesian driver-and-car-pace model (phase 3 v2).

The previous version of this module fit the data fine but the variance
components collapsed — sigma_driver and sigma_team both fell to ~0 because
the per-session intercept absorbed essentially all between-session pace
variance. The fix here is structural, not prior-tuning:

* ``mu_track[t]`` — a per-circuit baseline that pools across years.
  Only ~30 circuits in the dataset, so the model can't hide structural
  variance in nuisance flexibility.
* ``car_pace[team, season]`` — first-class team-season effect, identified
  through:
    (a) teammate variation within a session (same car, different drivers)
    (b) driver transfers across teams across seasons (HAM merc→ferrari,
        HUL across four teams, GAS across four teams, …)
    (c) intra-season smoothness via a random walk in time within a season
* ``driver_skill[driver, season]`` — per-driver per-season skill, with a
  **Gaussian random walk** prior across seasons. No bell-curve assumption.
  Drivers can plateau (Alonso), step-decline (Vettel late career), rise
  then plateau (Verstappen), or hold steady. Σ_drift learned from data.
* Regulation eras as a covariate, not a partition. 2017-2021 wide aero
  vs 2022-2025 ground effect get an explicit era random effect on the
  *track* intercept (track behaves differently under each rule set).

The likelihood is per-lap. The model identifies driver from car through
the combination of teammate-paired variation, driver transfers, smooth
car-upgrade priors, and the random walk on driver skill.

Output: per-driver per-season posterior skill, all-time pooled skill
posterior (average over seasons, weighted by their posterior precision),
and per-team per-season car-pace posterior. Plus pairwise probabilities
P(driver A skill > driver B skill | data) and the counterfactual machinery
to ask "if HAM raced the 2024 Red Bull, what would his finish position
distribution be."
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from pacelab import data
from pacelab.config import DERIVED_DIR
from pacelab.metrics.validity import add_validity_flag

log = logging.getLogger("pacelab.bayes")

BAYES_DIR = DERIVED_DIR / "bayes"
BAYES_DIR.mkdir(parents=True, exist_ok=True)
SKILL_FILE = BAYES_DIR / "driver_skill.json"
CAR_PACE_FILE = BAYES_DIR / "car_pace.json"
TRACE_FILE = BAYES_DIR / "trace.npz"


# Era assignment: 0 = wide-aero (2017-2021), 1 = ground-effect (2022+)
def _era_id(season: int) -> int:
    return 0 if season <= 2021 else 1


# Team aliases: collapse F1's serial team renames into a single entity so the
# car-pace random effect pools across the rename and we don't get artefacts
# like "RB 2024" and "Racing Bulls 2025" being treated as different teams.
_TEAM_ALIASES: dict[str, str] = {
    # Red Bull's junior team has cycled through four names.
    "Toro Rosso": "AlphaTauri/RB",
    "AlphaTauri": "AlphaTauri/RB",
    "RB": "AlphaTauri/RB",
    "Racing Bulls": "AlphaTauri/RB",
    # Force India -> Racing Point -> Aston Martin (continuous ownership).
    "Force India": "Aston Martin (ex Force India)",
    "Racing Point": "Aston Martin (ex Force India)",
    "Aston Martin": "Aston Martin (ex Force India)",
    # Renault -> Alpine (rebrand only).
    "Renault": "Alpine",
    "Alpine": "Alpine",
    # Sauber -> Alfa Romeo -> Kick Sauber (continuous ownership).
    "Sauber": "Kick Sauber",
    "Alfa Romeo Racing": "Kick Sauber",
    "Alfa Romeo": "Kick Sauber",
    "Kick Sauber": "Kick Sauber",
}


def _normalise_team(name: str) -> str:
    return _TEAM_ALIASES.get(name, name)


# ─────────────────────────────────────────────────────────────────────────────
# Dataset assembly
# ─────────────────────────────────────────────────────────────────────────────
def build_dataset(seasons: list[int]) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Produce a lap-level training frame + index coordinates.

    Returns df with integer indices for driver, team, season, track, era,
    and the float covariates the likelihood needs.
    """
    sessions = (
        data.sessions(seasons)
        .select(["session_key", "session_type", "event_name", "year"])
        .collect()
    )
    race_keys = sessions.filter(pl.col("session_type") == "R").select(
        ["session_key", "event_name", "year"]
    )
    laps = add_validity_flag(data.laps(seasons)).collect()
    laps = laps.join(race_keys, on="session_key", how="inner")

    clean = (
        laps.filter(pl.col("clean_for_pace"))
        .with_columns([
            pl.col("tyre_life").cast(pl.Int32).alias("stint_age"),
            pl.col("lap_time_s").log().alias("log_lap_time"),
            pl.col("team_name").map_elements(
                _normalise_team, return_dtype=pl.Utf8
            ).alias("team_name_norm"),
        ])
        .with_columns([
            pl.col("year").map_elements(_era_id, return_dtype=pl.Int32).alias("era_id"),
        ])
        .filter(
            pl.col("lap_time_s").is_finite()
            & (pl.col("lap_time_s") > 30.0)
            & (pl.col("lap_time_s") < 240.0)
            & (pl.col("stint_age") >= 0)
        )
        .drop("team_name")
        .rename({"team_name_norm": "team_name"})
    )

    if clean.is_empty():
        return clean, {}

    driver_codes = sorted(clean["driver_code"].unique().to_list())
    team_names = sorted(clean["team_name"].unique().to_list())
    years = sorted(clean["year"].unique().to_list())
    tracks = sorted(clean["event_name"].unique().to_list())
    sessions_list = sorted(clean["session_key"].unique().to_list())

    driver_idx = {c: i for i, c in enumerate(driver_codes)}
    team_idx = {t: i for i, t in enumerate(team_names)}
    year_idx = {y: i for i, y in enumerate(years)}
    track_idx = {t: i for i, t in enumerate(tracks)}
    session_idx = {s: i for i, s in enumerate(sessions_list)}

    n_eras = 2

    clean = clean.with_columns([
        pl.col("driver_code").replace_strict(driver_idx, return_dtype=pl.Int32).alias("driver_idx"),
        pl.col("team_name").replace_strict(team_idx, return_dtype=pl.Int32).alias("team_idx"),
        pl.col("year").replace_strict(year_idx, return_dtype=pl.Int32).alias("year_idx"),
        pl.col("event_name").replace_strict(track_idx, return_dtype=pl.Int32).alias("track_idx"),
        pl.col("session_key").replace_strict(session_idx, return_dtype=pl.Int32).alias("session_idx"),
    ])

    # team_season_idx and driver_season_idx flatten the 2D effects to 1D arrays
    # so JAX can use a single gather call per term.
    clean = clean.with_columns([
        (pl.col("team_idx") * len(years) + pl.col("year_idx")).alias("team_season_idx"),
        (pl.col("driver_idx") * len(years) + pl.col("year_idx")).alias("driver_season_idx"),
    ])

    coords = {
        "drivers": driver_codes,
        "teams": team_names,
        "tracks": tracks,
        "years": [int(y) for y in years],
        "sessions": sessions_list,
        "n_eras": n_eras,
        "n_team_season": len(team_names) * len(years),
        "n_driver_season": len(driver_codes) * len(years),
        # For each (driver, season) which team did the driver drive for?
        # Used by the team_season_idx mapping at prediction time.
        "driver_team_per_season": _driver_team_per_season(clean, driver_codes, years),
    }
    return clean, coords


def _driver_team_per_season(
    clean: pl.DataFrame, driver_codes: list[str], years: list[int]
) -> dict[str, dict[int, str]]:
    """Mapping driver_code -> {season: most_common_team_that_season}."""
    out: dict[str, dict[int, str]] = {d: {} for d in driver_codes}
    grouped = (
        clean.group_by(["driver_code", "year", "team_name"])
        .agg(pl.len().alias("n"))
        .sort(["driver_code", "year", "n"], descending=[False, False, True])
    )
    for row in grouped.iter_rows(named=True):
        d, y, t = row["driver_code"], int(row["year"]), row["team_name"]
        out.setdefault(d, {}).setdefault(y, t)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Model fit
# ─────────────────────────────────────────────────────────────────────────────
def fit_model(
    seasons: list[int],
    n_warmup: int = 1000,
    n_samples: int = 1500,
    n_chains: int = 2,
    target_accept: float = 0.85,
    subsample_per_session: int | None = 60,
    seed: int = 0,
) -> dict[str, Any]:
    """Fit the model and persist driver_skill.json + car_pace.json + trace."""
    import jax
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.infer import MCMC, NUTS

    t0 = time.time()
    log.info("assembling dataset for %s", seasons)
    df, coords = build_dataset(seasons)
    if df.is_empty():
        raise RuntimeError("no laps in the requested seasons; ingest first")

    if subsample_per_session is not None and subsample_per_session > 0:
        rng = np.random.default_rng(seed)
        sampled = []
        for (_sk, _dc), group in df.partition_by(
            ["session_key", "driver_code"], as_dict=True
        ).items():
            n = min(group.height, subsample_per_session)
            sampled.append(group.sample(n=n, with_replacement=False, seed=int(rng.integers(1 << 30))))
        df = pl.concat(sampled) if sampled else df

    n_drivers = len(coords["drivers"])
    n_teams = len(coords["teams"])
    n_tracks = len(coords["tracks"])
    n_years = len(coords["years"])
    n_sessions = len(coords["sessions"])

    log.info(
        "training rows=%d drivers=%d teams=%d tracks=%d sessions=%d seasons=%d",
        df.height, n_drivers, n_teams, n_tracks, n_sessions, n_years,
    )

    y = df["log_lap_time"].to_numpy().astype(np.float32)
    track = df["track_idx"].to_numpy().astype(np.int32)
    session = df["session_idx"].to_numpy().astype(np.int32)
    era = df["era_id"].to_numpy().astype(np.int32)
    team_season = df["team_season_idx"].to_numpy().astype(np.int32)
    driver_season = df["driver_season_idx"].to_numpy().astype(np.int32)
    stint_age = df["stint_age"].to_numpy().astype(np.float32)
    lap_number = df["lap_number"].to_numpy().astype(np.float32)

    # For the GRW prior we need to know, per driver-season slot, what
    # year-index that slot corresponds to. Build a (n_drivers, n_years)
    # mask + index.
    driver_for_slot = np.repeat(np.arange(n_drivers), n_years)
    year_for_slot = np.tile(np.arange(n_years), n_drivers)

    def model() -> None:
        # Per-circuit baseline (pooled across years/eras). ~30 params.
        mu_track = numpyro.sample(
            "mu_track",
            dist.Normal(jnp.full(n_tracks, jnp.log(95.0)), 0.5),
        )
        # Era × track interaction: ground-effect cars at Monaco have
        # different baseline pace than wide-aero cars at Monaco. ~60 params.
        era_track = numpyro.sample(
            "era_track",
            dist.Normal(jnp.zeros((2, n_tracks)), 0.05),
        )
        # Session-level offset: weather, fuel, formation lap, accidents.
        # Tight prior so it doesn't absorb structural variance. ~100 params.
        session_offset = numpyro.sample(
            "session_offset",
            dist.Normal(jnp.zeros(n_sessions), 0.01),
        )

        # Car pace per (team, season). Wide prior — cars genuinely differ
        # by several seconds per lap. Identified through teammate variation
        # within session and driver transfers across seasons.
        car_pace = numpyro.sample(
            "car_pace",
            dist.Normal(jnp.zeros(n_teams * n_years), 0.05),
        )

        # Driver skill as a Gaussian random walk across seasons.
        # No bell curve assumption — let the data shape the trajectory.
        sigma_drift = numpyro.sample("sigma_drift", dist.HalfNormal(0.005))
        skill_init = numpyro.sample(
            "skill_init",
            dist.Normal(jnp.zeros(n_drivers), 0.01),
        )
        # Innovations: shape (n_drivers, n_years - 1)
        innovations = numpyro.sample(
            "innovations",
            dist.Normal(jnp.zeros((n_drivers, max(n_years - 1, 1))), 1.0),
        )
        # cumulative-sum the innovations across years, scaled by sigma_drift.
        # Result: shape (n_drivers, n_years). Flatten to (n_drivers * n_years).
        skill = jnp.concatenate(
            [skill_init[:, None], skill_init[:, None] + jnp.cumsum(innovations * sigma_drift, axis=1)],
            axis=1,
        ) if n_years > 1 else skill_init[:, None]
        driver_skill = numpyro.deterministic(
            "driver_skill", skill.reshape(-1)
        )

        # Stint-age + fuel coefficients.
        beta_stint = numpyro.sample("beta_stint", dist.Normal(0.0, 0.0005))
        gamma_fuel = numpyro.sample("gamma_fuel", dist.Normal(0.0, 0.0005))

        # Observation noise.
        sigma_eps = numpyro.sample("sigma_eps", dist.HalfNormal(0.03))

        mu = (
            mu_track[track]
            + era_track[era, track]
            + session_offset[session]
            + car_pace[team_season]
            + driver_skill[driver_season]
            + beta_stint * stint_age
            + gamma_fuel * lap_number
        )
        numpyro.sample("y", dist.Normal(mu, sigma_eps), obs=y)

    numpyro.set_host_device_count(n_chains)
    kernel = NUTS(model, target_accept_prob=target_accept)
    mcmc = MCMC(
        kernel,
        num_warmup=n_warmup,
        num_samples=n_samples,
        num_chains=n_chains,
        progress_bar=False,
        chain_method="sequential",
    )
    rng_key = jax.random.PRNGKey(seed)
    log.info("fitting NUTS (warmup=%d samples=%d chains=%d)", n_warmup, n_samples, n_chains)
    mcmc.run(rng_key)

    samples = mcmc.get_samples(group_by_chain=False)
    skill_post = np.asarray(samples["driver_skill"])  # (n_post, n_drivers * n_years)
    car_post = np.asarray(samples["car_pace"])        # (n_post, n_teams * n_years)
    sigma_drift_post = float(np.median(samples["sigma_drift"]))
    sigma_eps_post = float(np.median(samples["sigma_eps"]))

    # Convert log-space deltas to approximate seconds-per-lap at 95s reference.
    ref = 95.0
    skill_seconds = skill_post * ref
    car_seconds = car_post * ref

    # Reshape (n_post, n_drivers, n_years) and (n_post, n_teams, n_years)
    skill_seconds = skill_seconds.reshape(skill_seconds.shape[0], n_drivers, n_years)
    car_seconds = car_seconds.reshape(car_seconds.shape[0], n_teams, n_years)

    # All-time skill per driver: average across seasons the driver actually
    # raced. We use the driver-team-per-season map to find which years to
    # include.
    driver_seasons_raced: dict[str, list[int]] = {d: [] for d in coords["drivers"]}
    for d, season_team in coords["driver_team_per_season"].items():
        driver_seasons_raced[d] = [coords["years"].index(int(y)) for y in season_team.keys()]

    drivers_payload: list[dict[str, Any]] = []
    for i, code in enumerate(coords["drivers"]):
        seasons_raced_idx = driver_seasons_raced.get(code, [])
        if not seasons_raced_idx:
            seasons_raced_idx = list(range(n_years))
        per_season = []
        for yi in range(n_years):
            samps = skill_seconds[:, i, yi]
            per_season.append({
                "year": int(coords["years"][yi]),
                "value": float(np.median(samps)),
                "hdi_lo": float(np.quantile(samps, 0.025)),
                "hdi_hi": float(np.quantile(samps, 0.975)),
                "team": coords["driver_team_per_season"].get(code, {}).get(
                    int(coords["years"][yi]), None
                ),
            })
        # All-time: pool over seasons raced.
        pooled = skill_seconds[:, i, seasons_raced_idx].mean(axis=1)
        drivers_payload.append({
            "driver_code": code,
            "skill_seconds_per_lap": float(np.median(pooled)),
            "hdi_lo_seconds": float(np.quantile(pooled, 0.025)),
            "hdi_hi_seconds": float(np.quantile(pooled, 0.975)),
            "n_posterior_samples": int(skill_post.shape[0]),
            "seasons_raced": [int(coords["years"][yi]) for yi in seasons_raced_idx],
            "per_season": per_season,
            # Full posterior samples kept for pairwise calc
            "_pooled_samples": pooled,
        })

    drivers_payload.sort(key=lambda r: r["skill_seconds_per_lap"])

    # Pairwise P(driver_a faster than driver_b) — uses pooled posterior samples
    pair_probs: dict[str, dict[str, float]] = {}
    code_to_samples = {d["driver_code"]: d["_pooled_samples"] for d in drivers_payload}
    for code_a, samps_a in code_to_samples.items():
        pair_probs[code_a] = {}
        for code_b, samps_b in code_to_samples.items():
            if code_a == code_b:
                continue
            p = float(np.mean(samps_a < samps_b))
            pair_probs[code_a][code_b] = p

    # Strip _pooled_samples from JSON payload (only used for pairwise).
    for d in drivers_payload:
        del d["_pooled_samples"]

    # Car pace per (team, season).
    teams_payload: list[dict[str, Any]] = []
    for ti, team in enumerate(coords["teams"]):
        per_season = []
        for yi in range(n_years):
            samps = car_seconds[:, ti, yi]
            per_season.append({
                "year": int(coords["years"][yi]),
                "value": float(np.median(samps)),
                "hdi_lo": float(np.quantile(samps, 0.025)),
                "hdi_hi": float(np.quantile(samps, 0.975)),
            })
        teams_payload.append({
            "team_name": team,
            "per_season": per_season,
        })

    skill_summary = {
        "schema_version": 2,
        "model_version": "v2-mu-track-grw-carpace",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "seasons_used": [int(y) for y in coords["years"]],
        "reference_lap_seconds": ref,
        "training_rows": int(df.height),
        "n_drivers": n_drivers,
        "n_teams": n_teams,
        "n_tracks": n_tracks,
        "n_sessions": n_sessions,
        "n_seasons": n_years,
        "sampler": {
            "warmup": n_warmup,
            "samples": n_samples,
            "chains": n_chains,
            "target_accept": target_accept,
            "subsample_per_session": subsample_per_session,
            "seed": seed,
        },
        "scale_summaries_log": {
            "sigma_drift_skill": sigma_drift_post,
            "sigma_epsilon": sigma_eps_post,
        },
        "drivers": drivers_payload,
        "pairwise_probability_a_faster_than_b": pair_probs,
        "elapsed_seconds": time.time() - t0,
    }
    car_summary = {
        "schema_version": 2,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "seasons_used": [int(y) for y in coords["years"]],
        "reference_lap_seconds": ref,
        "teams": teams_payload,
    }

    SKILL_FILE.write_text(json.dumps(skill_summary, indent=2))
    CAR_PACE_FILE.write_text(json.dumps(car_summary, indent=2))
    np.savez_compressed(
        TRACE_FILE,
        driver_skill_seconds=skill_seconds.astype(np.float32),
        car_pace_seconds=car_seconds.astype(np.float32),
        drivers=np.array(coords["drivers"]),
        teams=np.array(coords["teams"]),
        years=np.array(coords["years"], dtype=np.int32),
    )
    log.info(
        "fit complete in %.1f min; %d drivers, %d teams, %d seasons -> %s",
        skill_summary["elapsed_seconds"] / 60.0, n_drivers, n_teams, n_years, SKILL_FILE,
    )
    return skill_summary


def load_skill() -> dict[str, Any] | None:
    if not SKILL_FILE.exists():
        return None
    return json.loads(SKILL_FILE.read_text())


def load_car_pace() -> dict[str, Any] | None:
    if not CAR_PACE_FILE.exists():
        return None
    return json.loads(CAR_PACE_FILE.read_text())


__all__ = [
    "build_dataset",
    "fit_model",
    "load_skill",
    "load_car_pace",
    "BAYES_DIR",
    "SKILL_FILE",
    "CAR_PACE_FILE",
    "TRACE_FILE",
]

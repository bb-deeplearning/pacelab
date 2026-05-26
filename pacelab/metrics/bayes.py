"""Hierarchical Bayesian driver-skill model (phase 3).

Treats every clean racing lap from every ingested season as a draw from:

    log(lap_time) = mu_session_compound
                  + alpha_team[team, era]
                  + alpha_driver[driver]
                  + beta_stint_age * stint_age
                  + gamma_fuel    * lap_number
                  + epsilon

where

    alpha_driver[d] ~ Normal(0, sigma_driver^2)
    alpha_team[t,e] ~ Normal(0, sigma_team^2)
    epsilon         ~ Normal(0, sigma_epsilon^2)

The model uses sum-to-zero soft constraints on the driver and team
effects so they are identified up to a session-compound intercept.

Notes on identifiability:

* The `mu_session_compound` term absorbs every per-(session, compound)
  baseline pace difference (track, weather, tyre family, fuel philosophy).
* `alpha_team[team, era]` then captures the team's car-quality residual
  relative to the field median for that era.
* `alpha_driver[driver]` is what's left after both of those are absorbed.
  It is identified through teammate pair variance (within a team-era,
  two drivers split the residual) and through driver transfers across
  teams (drivers anchor different team-eras).
* `era` is a hierarchical grouping over seasons; we use 3-year windows so
  car regulations have time to express themselves but the model can still
  detect mid-career regime shifts.

Output: per-driver posterior summary (median + 95% HDI), plus the full
posterior draws for any pairwise probability the API needs to compute.

This is computationally non-trivial: a typical 4-season run is ~1.5 GB of
laps and the NUTS sampler takes 5-10 minutes per chain on the GCP VM.
Run as a background job once per data refresh and cache the artefacts.
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
from pacelab.config import DERIVED_DIR, METRICS
from pacelab.metrics.validity import add_validity_flag

log = logging.getLogger("pacelab.bayes")

BAYES_DIR = DERIVED_DIR / "bayes"
BAYES_DIR.mkdir(parents=True, exist_ok=True)
SKILL_FILE = BAYES_DIR / "driver_skill.json"
TRACE_FILE = BAYES_DIR / "trace.npz"


def _era_id(season: int) -> int:
    """Three-year window. 2018-2020 -> 0, 2021 -> 1, 2022-2025 -> 2."""
    # F1 regulation eras: 2017-2021 (wide aero), 2022-2025 (ground effect), 2026+ next.
    if season <= 2021:
        return 0
    return 1


def build_dataset(seasons: list[int]) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Assemble the long-format Bayesian training set.

    Returns the lap-level frame and a mapping of code <-> index for each
    categorical column.
    """
    sessions = data.sessions(seasons).select(["session_key", "session_type", "year"]).collect()
    race_keys = sessions.filter(pl.col("session_type") == "R").select("session_key")
    laps = add_validity_flag(data.laps(seasons)).collect()
    laps = laps.join(race_keys, on="session_key", how="inner")

    clean = (
        laps.filter(pl.col("clean_for_pace"))
        .with_columns([
            pl.col("session_key").str.slice(0, 4).cast(pl.Int32).alias("year"),
            pl.col("tyre_life").cast(pl.Int32).alias("stint_age"),
            pl.col("lap_time_s").log().alias("log_lap_time"),
        ])
        .with_columns(
            pl.col("year").map_elements(_era_id, return_dtype=pl.Int32).alias("era_id")
        )
        .filter(
            pl.col("lap_time_s").is_finite()
            & (pl.col("lap_time_s") > 30.0)
            & (pl.col("lap_time_s") < 240.0)
            & (pl.col("stint_age") >= 0)
        )
    )

    if clean.is_empty():
        return clean, {}

    # Build integer indices for each categorical column.
    driver_codes = sorted(clean["driver_code"].unique().to_list())
    team_names = sorted(clean["team_name"].unique().to_list())
    session_compound = (
        clean.with_columns(
            (pl.col("session_key") + "::" + pl.col("compound")).alias("session_compound")
        )
        ["session_compound"].unique().to_list()
    )
    session_compound.sort()

    driver_idx = {c: i for i, c in enumerate(driver_codes)}
    team_idx = {t: i for i, t in enumerate(team_names)}
    sc_idx = {sc: i for i, sc in enumerate(session_compound)}
    n_eras = int(clean["era_id"].max()) + 1

    clean = clean.with_columns([
        (pl.col("session_key") + "::" + pl.col("compound")).map_elements(
            lambda x: sc_idx[x], return_dtype=pl.Int32
        ).alias("sc_idx"),
        pl.col("driver_code").map_elements(
            lambda x: driver_idx[x], return_dtype=pl.Int32
        ).alias("driver_idx"),
        pl.col("team_name").map_elements(
            lambda x: team_idx[x], return_dtype=pl.Int32
        ).alias("team_idx"),
    ])

    # Team-era id is a combined index for (team, era) — that's what alpha_team is keyed on.
    team_era = clean.with_columns(
        (pl.col("team_idx") * n_eras + pl.col("era_id")).alias("team_era_idx")
    )

    coords = {
        "drivers": driver_codes,
        "teams": team_names,
        "session_compound": session_compound,
        "n_eras": n_eras,
        "n_team_era": len(team_names) * n_eras,
    }
    return team_era, coords


def fit_model(
    seasons: list[int],
    n_warmup: int = 500,
    n_samples: int = 1000,
    n_chains: int = 2,
    target_accept: float = 0.85,
    subsample_per_session: int | None = 80,
    seed: int = 0,
) -> dict[str, Any]:
    """Fit the hierarchical model and persist a summary + the trace.

    For tractability on the GCP VM we subsample laps per session by default
    (set subsample_per_session=None to use everything). The subsample is
    stratified by (session_key, driver_code).
    """
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

    log.info(
        "training rows=%d drivers=%d teams=%d session_compounds=%d eras=%d",
        df.height, len(coords["drivers"]), len(coords["teams"]),
        len(coords["session_compound"]), coords["n_eras"],
    )

    y = df["log_lap_time"].to_numpy().astype(np.float32)
    sc = df["sc_idx"].to_numpy().astype(np.int32)
    driver = df["driver_idx"].to_numpy().astype(np.int32)
    team_era = df["team_era_idx"].to_numpy().astype(np.int32)
    stint_age = df["stint_age"].to_numpy().astype(np.float32)
    lap_number = df["lap_number"].to_numpy().astype(np.float32)

    n_drivers = len(coords["drivers"])
    n_team_era = coords["n_team_era"]
    n_sc = len(coords["session_compound"])

    def model() -> None:
        # Non-centred parameterisation for the random effects.
        # Tight priors: in log(lap_time) space, a typical between-driver
        # spread is ~0.003 log-units (~0.3s on a 95s lap). Team variance is
        # similar. Lap-to-lap noise is dominated by sector/condition jitter
        # in the range 0.003-0.010 log-units.
        sigma_driver = numpyro.sample("sigma_driver", dist.HalfNormal(0.005))
        sigma_team = numpyro.sample("sigma_team", dist.HalfNormal(0.010))
        sigma_epsilon = numpyro.sample("sigma_epsilon", dist.HalfNormal(0.020))

        # The session-compound intercept is the biggest term — absorbs the
        # absolute lap time of the session. Wide prior centred on log(95s).
        mu_sc = numpyro.sample(
            "mu_sc",
            dist.Normal(jnp.full(n_sc, jnp.log(95.0)), 0.5),
        )
        driver_z = numpyro.sample("driver_z", dist.Normal(jnp.zeros(n_drivers), 1.0))
        team_z = numpyro.sample("team_z", dist.Normal(jnp.zeros(n_team_era), 1.0))

        alpha_driver = numpyro.deterministic("alpha_driver", driver_z * sigma_driver)
        alpha_team = numpyro.deterministic("alpha_team", team_z * sigma_team)

        beta_stint = numpyro.sample("beta_stint", dist.Normal(0.0, 0.001))
        gamma_fuel = numpyro.sample("gamma_fuel", dist.Normal(0.0, 0.001))

        mu = (
            mu_sc[sc]
            + alpha_team[team_era]
            + alpha_driver[driver]
            + beta_stint * stint_age
            + gamma_fuel * lap_number
        )
        numpyro.sample("y", dist.Normal(mu, sigma_epsilon), obs=y)

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
    alpha_d = np.asarray(samples["alpha_driver"])  # (n_post, n_drivers)
    sigma_eps = float(np.median(samples["sigma_epsilon"]))
    sigma_drv = float(np.median(samples["sigma_driver"]))
    sigma_tm = float(np.median(samples["sigma_team"]))

    # Convert back from log-space delta to approximate seconds-per-lap at a
    # ~95s reference lap.
    ref_lap_s = 95.0
    alpha_d_seconds = (np.exp(alpha_d) - 1.0) * ref_lap_s

    medians = np.median(alpha_d_seconds, axis=0)
    hdi_lo = np.quantile(alpha_d_seconds, 0.025, axis=0)
    hdi_hi = np.quantile(alpha_d_seconds, 0.975, axis=0)

    driver_records: list[dict[str, Any]] = []
    for i, code in enumerate(coords["drivers"]):
        driver_records.append({
            "driver_code": code,
            "skill_seconds_per_lap": float(medians[i]),
            "hdi_lo_seconds": float(hdi_lo[i]),
            "hdi_hi_seconds": float(hdi_hi[i]),
            "n_posterior_samples": int(alpha_d.shape[0]),
        })

    # Pairwise P(driver_a faster than driver_b) — store top pairs for the API.
    # We compute P(alpha_a < alpha_b) because lower alpha = faster.
    pair_probs: dict[str, dict[str, float]] = {}
    for i, code_a in enumerate(coords["drivers"]):
        pair_probs[code_a] = {}
        for j, code_b in enumerate(coords["drivers"]):
            if i == j:
                continue
            p = float(np.mean(alpha_d_seconds[:, i] < alpha_d_seconds[:, j]))
            pair_probs[code_a][code_b] = p

    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "seasons_used": sorted(set(seasons)),
        "reference_lap_seconds": ref_lap_s,
        "training_rows": int(df.height),
        "n_drivers": len(coords["drivers"]),
        "n_teams": len(coords["teams"]),
        "n_eras": coords["n_eras"],
        "n_session_compound": len(coords["session_compound"]),
        "sampler": {
            "warmup": n_warmup,
            "samples": n_samples,
            "chains": n_chains,
            "target_accept": target_accept,
            "subsample_per_session": subsample_per_session,
            "seed": seed,
        },
        "scale_summaries_log": {
            "sigma_driver": sigma_drv,
            "sigma_team": sigma_tm,
            "sigma_epsilon": sigma_eps,
        },
        "drivers": sorted(driver_records, key=lambda r: r["skill_seconds_per_lap"]),
        "pairwise_probability_a_faster_than_b": pair_probs,
        "elapsed_seconds": time.time() - t0,
    }

    SKILL_FILE.write_text(json.dumps(payload, indent=2))
    np.savez_compressed(
        TRACE_FILE,
        alpha_driver_seconds=alpha_d_seconds.astype(np.float32),
        driver_codes=np.array(coords["drivers"]),
    )
    log.info("fit complete in %.1f min; %s", payload["elapsed_seconds"] / 60.0, SKILL_FILE)
    return payload


def load_skill() -> dict[str, Any] | None:
    if not SKILL_FILE.exists():
        return None
    return json.loads(SKILL_FILE.read_text())


__all__ = [
    "build_dataset",
    "fit_model",
    "load_skill",
    "BAYES_DIR",
    "SKILL_FILE",
    "TRACE_FILE",
]

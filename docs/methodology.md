# Methodology

This document is the source of truth for how every number on a pacelab driver page is computed. If you are tempted to cite a pacelab metric somewhere, read the relevant section here first.

The guiding principle is **identifiability before precision**. There is enormous lap-time variation across the grid that has nothing to do with driver skill — the car, the tyre stint, the fuel mass, the track temperature, the traffic, the strategy call. Most of that variance is bigger than the skill signal we want. If a metric does not separate driver from those confounders, it is not on the site, no matter how easy it would be to compute.

## Conventions

- **Time window**: unless otherwise noted, a "season" metric uses all valid laps for that driver in that season. Long windows reduce variance; short windows surface form changes. Both views are exposed via the API.
- **Valid laps**: we exclude laps with deleted times (track limits), in-laps, out-laps, safety car / VSC laps, the first racing lap of every stint (tyre warm-up), pit-in laps, pit-out laps, and any lap with a yellow flag in any sector. The set of exclusion flags is recorded per lap in the Parquet schema and is reproducible.
- **Compound normalisation**: tyre compounds are recorded as `{SOFT, MEDIUM, HARD, INTERMEDIATE, WET, UNKNOWN}`. Compound is part of every per-lap join key.
- **Reference**: most metrics are reported as a **delta vs teammate on the same session**, because that is the cleanest car-controlled comparison. Where a grid-wide reference is more useful, the metric is reported as a delta from the session's pace median (with the driver's own and teammate's laps excluded from the median to prevent self-reference).
- **Uncertainty**: every metric publishes a 95% confidence interval (or, where applicable, a highest density interval from the posterior of a hierarchical model). Intervals are computed by stratified bootstrap unless the underlying statistic has a well-known closed-form variance.

## The identifiability problem

The naive regression is:

```
lap_time = f(car, driver, track, weather, tyres, fuel, traffic, strategy, era, …)
```

For any individual driver in any individual season, `driver` and `car` are perfectly collinear: that driver drives that car and only that car. You cannot extract `driver` from `lap_time` alone. The variation that breaks the collinearity, in order of signal strength:

1. **Teammate comparisons** — same car, same garage, same engineers. Gold standard.
2. **Driver transfers across teams** — before-and-after for the same driver in different cars.
3. **The teammate graph traversed across seasons** — chains of teammate pairs let you connect drivers who were never teammates directly, the same way chess Elo connects players through shared opponents.
4. **High-variance conditions** (wet, mixed, restarts) — the driver share of total lap-time variance rises sharply.

Phases 1 and 2 of pacelab rely entirely on (1) and (4). Phase 3 adds (2) and (3) via a hierarchical Bayesian model fit over the full teammate graph 2018→present.

## Phase 1 metrics

### Teammate-adjusted qualifying pace

**Definition.** Median, across qualifying sessions in the window, of `(driver_best_qual_lap − teammate_best_qual_lap)` where both drivers reached the same qualifying segment.

**Computation.**

1. For each Grand Prix in the window, identify the driver's best representative qualifying lap and the teammate's best lap *in the same segment* (Q1, Q2, or Q3). If they did not share a segment, the session is skipped.
2. The per-session delta is `driver_best − teammate_best` in seconds.
3. Report the median over sessions and a 95% bootstrap CI (10,000 resamples, percentile method).

**Why median over mean.** A red flag, mechanical failure, or out-lap mishap can produce a several-second outlier in a single session. The median is robust to those.

**Known confounders.**

- *Unequal cars on the day.* A team will sometimes prioritise one driver's setup. We do not currently correct for this — assumed to wash out over a season but flagged in the metric description on the page.
- *#1/#2 dynamics.* The lead driver may get the newer aero parts first. Same caveat.
- *Different fuel loads.* Q1 vs Q3 fuel is essentially the same (low). Within a session, same.

### Teammate-adjusted race pace

**Definition.** For each Grand Prix in the window, compute the per-lap median delta between the driver's clean race laps and the teammate's clean race laps within the **same stint window on the same compound**. Aggregate across races by median; report 95% bootstrap CI.

**Computation.**

1. For each race, segment both drivers' laps into stints by compound and pit stop.
2. Identify "matched" stint pairs: same compound, same race, with at least 5 overlapping clean laps. A clean lap is one passing the validity filter described above AND not within 1.0 s of another car (to exclude traffic-bound laps).
3. For each matched pair, fit a linear pace decay (`lap_time = α + β·stint_age + γ·fuel_burn(lap)` where `fuel_burn` uses a fixed coefficient of 0.030 s/lap as a first approximation; this is a known F1 rule-of-thumb for fuel-corrected pace and is replaced in phase 3 with a fitted per-race coefficient).
4. The per-stint delta is `α_driver − α_teammate` (the intercept difference, i.e. the underlying pace after de-trending stint age and fuel).
5. Median across stints, then median across races. 95% bootstrap CI on the per-race medians.

**Known confounders.**

- *Strategy*: if one driver was pitted long while the teammate was pitted short, the stints they actually drove may not be comparable. The "matched stints" filter handles this for first-order effects but not for cases where one driver was managing tyres for a long stint while the other was pushing.
- *Track evolution*: this is partially absorbed by including both drivers' laps in the same time window, but not perfectly. Documented in the metric description.

### Tyre degradation

**Definition.** For each stint of ≥ 5 clean laps, fit `lap_time = α + β·stint_age + γ·fuel_burn(lap)` with `γ = 0.030` s/lap fixed. The driver's degradation slope on that compound is the per-driver weighted median of `β` across stints, weighted by stint length. Reported per compound, with a teammate delta.

**Interpretation.** Lower β = better tyre management on that compound. The teammate delta is the cleanest comparison: same car, same race, same compound.

**Known confounders.** Strategy and traffic again. The clean-lap filter helps; phase 2 will replace this with a non-linear (typically log-linear) decay model fit that is more robust to push laps near the end of a stint.

### Wet vs dry skill

**Definition.** For each wet-classified session (rainfall > 0 mm at any point per FastF1 weather data, OR ≥ 1 driver on intermediate/wet tyres for a substantial fraction of the session), compute the driver's teammate-adjusted race pace delta. Average across wet sessions and subtract the driver's dry baseline (the same metric computed over dry sessions only in the same window).

**Interpretation.** Positive number = the driver gains time relative to teammate when conditions get wet, beyond what the car gains. Negative = the driver loses time in the wet relative to teammate.

**Known confounders.** Wet sessions are rare (typically 2–4 per year). Reported with a wide CI by definition. Where the sample size is small (< 4 wet sessions), a "low sample" warning is rendered next to the number.

### Stint consistency

**Definition.** Per stint of ≥ 5 clean laps, compute the residual from the fit `lap_time = α + β·stint_age + γ·fuel_burn(lap)`. The consistency metric is the standard deviation of those residuals. Lower = more consistent. Reported as a season median across stints, with a teammate delta.

**Interpretation.** This is a pure intra-stint variance estimate after removing tyre-age and fuel trend. It is one of the cleanest car-independent driver signals available from public data.

### Wheel-to-wheel pace retention (dirty-air tax)

**Definition.** Mean per-lap delta when the driver is within 1.0 s of the car ahead (per FastF1 `LapStartTime` and gap-to-leader timing data), minus the same driver's mean per-lap delta in free air, normalised to the session's median dirty-air penalty for the comparison.

**Caveat.** The 1.0 s threshold is a heuristic; the actual dirty-air boundary varies by car generation (2022+ ground-effect cars suffer less than 2017–2021 cars). The metric is reported as a delta vs the field median for that car generation.

### Error rate

**Definition.** Number of "error events" per race, where an error event is any of:

- A wheel-speed lock > 8% under braking (detected from telemetry: wheel speeds drop below ground speed)
- A lap-time spike > 1.5 s above the driver's stint-fitted pace, not coinciding with traffic or pit operations
- An off-track event detected by an unexpected position deviation from the racing line of ≥ 5 m (the racing line is computed as the centroid of the field's positions through that corner over the session)

Each event type is also reported individually.

**Caveat.** Telemetry-derived events are imperfect: some lockups go undetected (small ones) and some racing-line deviations are deliberate (defending). Documented per-event.

### Recovery (positions gained)

**Definition.** `(grid_position − finish_position)`, adjusted for the average grid-to-finish delta of drivers in similar grid slots over a 3-year rolling window, with DNFs handled as right-censored at the position at retirement.

**Caveat.** Safety cars create luck. We do not currently adjust for this beyond reporting the per-race attribution alongside the metric. Phase 2 will add a SC-adjusted recovery metric using the historical SC distribution per track.

## Phase 2 (planned)

Telemetry-level driving-style fingerprints, intended to characterise *how* a driver drives independently of *how fast*:

- Braking precision (variance from per-corner optimal braking model)
- Throttle modulation smoothness (integrated jerk over corner exits)
- Apex aggression (% of car's theoretical grip used mid-corner)
- Out-lap and in-lap tyre warm-up effectiveness

## Phase 3 (planned)

Hierarchical Bayesian model fit over the full 2018→present teammate graph. Schematically:

```
log(lap_time) ~ Normal(μ, σ²)
μ = base_pace[track, conditions]
  + car_quality[team, season, upgrade_window]
  + driver_skill[driver]
  + driver_track_interaction[driver, track_type]
  + driver_condition_interaction[driver, weather]
  + tyre_state(stint_age, compound, temp)
  + fuel_load(lap, race)
  + traffic_penalty(gap_to_car_ahead)

driver_skill[d] ~ Normal(0, σ_d²)
car_quality[c]  ~ Normal(0, σ_c²)
```

Fit via NumPyro / NUTS. Produces full posterior on every term, including era-spanning driver skill distributions and posterior probabilities of head-to-head comparisons.

## Prior art and references

- Bell, A., Smith, J., Sampaio, C. (2016). *Formula for success: multilevel modelling of Formula One driver and constructor performance, 1950–2014.* Journal of Quantitative Analysis in Sports.
- Eichenberger, R., Stadelmann, D. (2009). *Who is the best Formula 1 driver? An economic approach to evaluating talent.* Economic Analysis & Policy.
- Heilmeier, A., Geisslinger, M., Betz, J. (2020). *A quasi-steady-state lap time simulator for electrified racing vehicles.* (And related TUM race-strategy papers.)
- Wieser, E. (2020). *The Formula One driver-versus-car problem* — Bayesian hierarchical analysis on teammate graph.

## What this site is not

- It is not a ranking. The phase 1 outputs are not designed to support a scalar ordering of drivers, because skill is multi-dimensional and any single ordering loses most of the signal.
- It is not a model of any individual team's car beyond what teammate comparisons reveal.
- It is not a prediction engine — yet. Phase 3 produces probabilistic head-to-head comparisons but does not predict race outcomes; that is downstream work.

If you think a metric is computed incorrectly, open an issue with a worked example. The whole point is that every number is checkable.

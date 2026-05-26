# pacelab

> Evidence-based driver scouting reports for Formula 1.
>
> Every number on every page has a derivation, a sample size, and a confidence interval. Punditry is fine. Vibes are not data.

## Why this exists

Most published F1 driver rankings are built on observation and recency bias. Pundits ride the last race. Fans absorb storylines that get repeated. The actual data — lap-by-lap timing, 3.7 Hz car positions, sector splits, tyre stints, race control messages — has been freely available for years and is barely used outside team strategy rooms and a small group of researchers.

This is the gap. pacelab pulls the public data (via [FastF1](https://github.com/theOehrly/Fast-F1)) for every session from 2018 onwards, computes a profile per driver from teammate-paired and condition-controlled comparisons, and renders it as a scouting report — one page per driver. The math is well-known applied statistics, mostly hierarchical models and careful pair-wise inference. The contribution is the rigour and the presentation: nothing on a page that you cannot click into and see the derivation for.

## What it produces

Per driver:

- **Teammate-adjusted qualifying and race pace** (median delta, with 95% CI)
- **Tyre management** — degradation slope per compound, vs teammate on same stint
- **Wet vs dry skill** — delta isolated from car's wet capability via teammate split
- **Stint consistency** — intra-stint SD of lap time after de-trending fuel + tyre wear
- **Wheel-to-wheel pace retention** — dirty-air tax measured directly
- **Error rate** — offs, lockups and lap-time spikes per race, extracted from telemetry
- **Recovery** — positions gained net of grid, normalised for SC/VSC and others' DNFs
- **Track-type breakdowns** — strengths by circuit category, not by reputation

Each metric shows: the value, the data window, the sample size, the comparator (teammate, grid median, or self), and a one-paragraph plain-English derivation. A driver page is a scouting report you can defend, not a leaderboard.

## Status

| Phase | Scope | State |
| ----- | ----- | ----- |
| 0 | Data foundation: FastF1 → Parquet ingest, schema, backfill CLI | done |
| 1 | Descriptive teammate-adjusted metrics + driver page UI | done |
| 2 | Telemetry-level style fingerprints (braking, throttle smoothness, apex aggression) | planned |
| 3 | Hierarchical Bayesian skill model spanning the teammate graph | planned |
| 4 | Live mode during race weekends (SignalR ingest, live strategy sim) | planned |

## Architecture

```
                         ┌──────────────────────────────┐
                         │       FastF1 archive         │
                         │  (laps, telemetry, results)  │
                         └──────────────┬───────────────┘
                                        │ ingest
                                        ▼
                          ┌──────────────────────────┐
                          │   data/parquet/*.parquet │
                          │   (sessions, laps,       │
                          │    stints, drivers, ...) │
                          └──────────────┬───────────┘
                                         │ DuckDB
                                         ▼
                          ┌──────────────────────────┐
                          │   pacelab.metrics.*      │
                          │   (one module per        │
                          │    well-defined metric)  │
                          └──────────────┬───────────┘
                                         │
                                         ▼
                          ┌──────────────────────────┐
                          │   FastAPI service        │
                          │   /api/drivers/{code}    │
                          └──────────────┬───────────┘
                                         │
                                         ▼
                          ┌──────────────────────────┐
                          │   Next.js + Tailwind UI  │
                          │   /drivers/{code}        │
                          └──────────────────────────┘
```

## Quick start

### Prerequisites

* Python 3.11+ (3.11 specifically works; 3.12 and 3.13 should work but are untested).
* [uv](https://github.com/astral-sh/uv) is recommended for the Python environment. `pip` works too.
* [bun](https://bun.sh) for the web UI. `npm` and `pnpm` work too.
* ~30 GB free disk for the full 2018→present FastF1 cache.

### Set up

```bash
# Python env (uv recommended)
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"

# Web env
cd web && bun install && cd ..
```

### Ingest, build metrics, run

```bash
# 1. Backfill data from FastF1 — most recent seasons first so you can ship
#    a useful site before the older years are pulled.
#    The FastF1/Ergast 500-calls/hour rate-limit will abort the run; resume
#    by re-running the same command after ~hour.
pacelab ingest backfill --from 2024 --to 2025
pacelab ingest backfill --from 2022 --to 2023
pacelab ingest backfill --from 2018 --to 2021

# 2. Compute metric profiles per season.
pacelab metrics build --seasons 2018,2019,2020,2021,2022,2023,2024,2025

# 3. Run the API + web together.
./scripts/dev.sh
# api:  http://127.0.0.1:8200
# web:  http://127.0.0.1:4400
```

### CLI cheat sheet

```bash
pacelab ingest status              # what's been ingested per year
pacelab ingest backfill --help     # ingest flags
pacelab metrics build --seasons 2024,2025
pacelab serve api --port 8200
```

## Data sources

- **[FastF1](https://github.com/theOehrly/Fast-F1)** — primary historical archive (lap times, sector splits, tyre stints, weather, car telemetry at 3.7 Hz, race control messages, results). MIT-licensed Python wrapper around F1's own live timing archive plus the Ergast historical data.
- **[OpenF1](https://openf1.org)** — secondary, used during live race weekends.
- **F1 SignalR live timing** — direct websocket source, planned for phase 4.

## Methodology

Read [`docs/methodology.md`](docs/methodology.md) before drawing any conclusion from a number on this site. It documents how every metric is computed, what the known confounders are, and where the math will and won't hold up.

## License

MIT. See [LICENSE](LICENSE).

## Disclaimer

pacelab is unofficial and is not associated in any way with Formula 1, the FIA, or any team. *Formula 1, F1, GRAND PRIX, PADDOCK CLUB,* and related marks are trade marks of Formula One Licensing B.V.

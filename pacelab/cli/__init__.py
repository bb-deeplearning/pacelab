"""pacelab command-line interface."""

from __future__ import annotations

import logging
import sys

import click
from rich.console import Console
from rich.table import Table

from pacelab.config import INGEST, PARQUET_DIR

console = Console()


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet FastF1's chattier modules at INFO.
    if not verbose:
        for noisy in ("fastf1.fastf1.req", "fastf1.api", "fastf1.fastf1.core"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """pacelab — evidence-based driver scouting reports for Formula 1."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    _configure_logging(verbose)


# ─────────────────────────────────────────────────────────────────────────────
# ingest
# ─────────────────────────────────────────────────────────────────────────────
@main.group()
def ingest() -> None:
    """Download and persist FastF1 data to Parquet."""


@ingest.command("backfill")
@click.option("--from", "from_year", type=int, default=INGEST.earliest_year,
              help=f"First season to ingest (default {INGEST.earliest_year}).")
@click.option("--to", "to_year", type=int, default=INGEST.latest_year,
              help=f"Last season to ingest (default {INGEST.latest_year}).")
@click.option("--session-types", default="Q,R,S,SQ",
              help="Comma-separated session types: Q,R,S,SQ,FP1,FP2,FP3.")
@click.option("--force", is_flag=True, help="Re-ingest sessions that already exist.")
@click.option("--pause-on-rate-limit", type=float, default=None,
              help="If set, pause this many seconds and retry on rate limit. "
                   "By default we abort the run when rate-limited.")
def ingest_backfill(
    from_year: int, to_year: int, session_types: str, force: bool,
    pause_on_rate_limit: float | None,
) -> None:
    """Backfill seasons FROM..TO (inclusive). Skips completed sessions unless --force."""
    from pacelab.ingest import backfill

    types = tuple(t.strip().upper() for t in session_types.split(",") if t.strip())
    console.print(f"[bold]ingesting[/bold] {from_year}..{to_year} sessions={list(types)}")
    report = backfill(
        from_year, to_year,
        session_types=types, force=force,
        pause_on_rate_limit_s=pause_on_rate_limit,
    )
    console.print()
    console.rule("[bold]ingest report")
    console.print(f"attempted : [bold]{report.attempted}[/bold]")
    console.print(f"succeeded : [green]{report.succeeded}[/green]")
    console.print(f"skipped   : [yellow]{report.skipped}[/yellow] (already present)")
    console.print(f"failed    : [red]{len(report.failed)}[/red]")
    if report.failed:
        t = Table(show_header=True, title="failures")
        t.add_column("session")
        t.add_column("error")
        for key, err in report.failed[:25]:
            t.add_row(key, err[:120])
        console.print(t)
        if len(report.failed) > 25:
            console.print(f"... and {len(report.failed) - 25} more")
    console.print(f"elapsed   : {report.elapsed_s/60:.1f} min")


@ingest.command("telemetry")
@click.option("--from", "from_year", type=int, default=INGEST.latest_year,
              help="First season to pull telemetry for.")
@click.option("--to", "to_year", type=int, default=INGEST.latest_year,
              help="Last season to pull telemetry for.")
@click.option("--session-types", default="R",
              help="Session types for telemetry (default R-only since telemetry is heavy).")
def ingest_telemetry(from_year: int, to_year: int, session_types: str) -> None:
    """Pull telemetry for already-ingested sessions. Heavy; usually opt-in per year."""
    from pacelab.ingest.telemetry import backfill_telemetry

    types = tuple(t.strip().upper() for t in session_types.split(",") if t.strip())
    console.print(f"[bold]pulling telemetry[/bold] {from_year}..{to_year} sessions={list(types)}")
    report = backfill_telemetry(from_year, to_year, session_types=types)
    console.print()
    console.print(f"sessions attempted : [bold]{report.sessions_attempted}[/bold]")
    console.print(f"sessions succeeded : [green]{report.sessions_succeeded}[/green]")
    console.print(f"lap frames written : [cyan]{report.n_lap_frames}[/cyan]")
    console.print(f"failed             : [red]{len(report.failed)}[/red]")
    if report.failed:
        for key, err in report.failed[:10]:
            console.print(f"  {key}: {err[:100]}")
    console.print(f"elapsed            : {report.elapsed_s/60:.1f} min")


@ingest.command("status")
def ingest_status() -> None:
    """Show how many sessions are ingested per year."""
    import polars as pl

    rows: list[dict] = []
    for year_dir in sorted(PARQUET_DIR.glob("year=*")):
        year = int(year_dir.name.split("=")[1])
        n_sessions = sum(
            1 for _ in year_dir.glob("round=*/session=*/laps.parquet")
        )
        rows.append({"year": year, "sessions_ingested": n_sessions})
    if not rows:
        console.print("[yellow]no ingested data yet.[/yellow] run: pacelab ingest backfill --from 2024")
        return
    t = Table(show_header=True, title="ingested sessions")
    t.add_column("year", justify="right")
    t.add_column("sessions", justify="right")
    for r in rows:
        t.add_row(str(r["year"]), str(r["sessions_ingested"]))
    console.print(t)


# ─────────────────────────────────────────────────────────────────────────────
# metrics
# ─────────────────────────────────────────────────────────────────────────────
@main.group()
def metrics() -> None:
    """Compute and persist driver metrics."""


@metrics.command("build")
@click.option("--seasons", default="2024,2025",
              help="Comma-separated list of seasons to compute metrics for.")
def metrics_build(seasons: str) -> None:
    """Compute driver metrics for the listed seasons and persist as derived artefacts."""
    from pacelab.metrics import build_all

    season_list = [int(s.strip()) for s in seasons.split(",") if s.strip()]
    console.print(f"[bold]building metrics for seasons:[/bold] {season_list}")
    summary = build_all(season_list)
    console.print(f"computed [green]{summary['n_drivers']}[/green] driver profiles "
                  f"across {summary['n_seasons']} season(s) in {summary['elapsed_s']:.1f}s")
    console.print(f"output: [dim]{summary['output_path']}[/dim]")


# ─────────────────────────────────────────────────────────────────────────────
# serve
# ─────────────────────────────────────────────────────────────────────────────
@main.group()
def serve() -> None:
    """Run pacelab's services."""


@serve.command("api")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8200, type=int)
@click.option("--reload", is_flag=True)
def serve_api(host: str, port: int, reload: bool) -> None:
    """Run the FastAPI service exposing computed driver metrics."""
    import uvicorn

    console.print(f"[bold]serving[/bold] http://{host}:{port}")
    uvicorn.run("pacelab.api.app:app", host=host, port=port, reload=reload, log_level="info")


if __name__ == "__main__":
    main(prog_name="pacelab")

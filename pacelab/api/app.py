"""FastAPI service exposing pacelab's computed driver profiles."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from pacelab.metrics import INDEX_FILE, PROFILES_DIR

app = FastAPI(
    title="pacelab",
    description="Evidence-based driver scouting reports for Formula 1.",
    version="0.1.0",
)

# Local UI runs on a different port; tailnet may have multiple origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _sanitize_for_json(obj: Any) -> Any:
    """Replace NaN/+Inf/-Inf with None so JSON serialisation is RFC-compliant."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def _json_response(data: Any) -> Response:
    return Response(
        content=json.dumps(_sanitize_for_json(data), default=str),
        media_type="application/json",
    )


def _load_index() -> dict[str, Any]:
    if not INDEX_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail="metrics index not built. run: pacelab metrics build",
        )
    return json.loads(INDEX_FILE.read_text())


def _profile_path(season: int, code: str) -> Path:
    return PROFILES_DIR / f"{season}_{code.upper()}.json"


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "pacelab",
        "version": app.version,
        "index_present": INDEX_FILE.exists(),
    }


@app.get("/api/index")
def index() -> Response:
    return _json_response(_load_index())


@app.get("/api/drivers")
def drivers(season: int | None = None) -> Response:
    """List drivers, optionally restricted to a season."""
    idx = _load_index()
    drivers_list = idx.get("drivers", [])
    if season is not None:
        drivers_list = [d for d in drivers_list if d.get("season") == season]
    return _json_response({"season": season, "count": len(drivers_list), "drivers": drivers_list})


@app.get("/api/drivers/{season}/{code}")
def driver_profile(season: int, code: str) -> Response:
    path = _profile_path(season, code)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"no profile for {season}/{code}")
    return _json_response(json.loads(path.read_text()))


@app.get("/api/seasons/{season}/leaderboards")
def season_leaderboards(season: int) -> Response:
    from pacelab.metrics.leaderboards import LEADERBOARDS_DIR
    p = LEADERBOARDS_DIR / f"{season}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"no leaderboards for {season}")
    return _json_response(json.loads(p.read_text()))


@app.get("/api/seasons/{season}/teammates")
def season_teammates(season: int) -> Response:
    from pacelab.metrics.teammates_h2h import TEAMMATES_DIR
    p = TEAMMATES_DIR / f"{season}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"no teammate h2h for {season}")
    return _json_response(json.loads(p.read_text()))


@app.get("/api/seasons")
def seasons() -> Response:
    idx = _load_index()
    return _json_response({"seasons": idx.get("seasons", [])})


__all__ = ["app"]

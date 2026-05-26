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


@app.get("/api/careers")
def careers() -> Response:
    from pacelab.metrics.career import CAREERS_FILE
    if not CAREERS_FILE.exists():
        raise HTTPException(status_code=503, detail="careers not built. run: pacelab metrics build")
    return _json_response(json.loads(CAREERS_FILE.read_text()))


@app.get("/api/careers/{code}")
def driver_career(code: str) -> Response:
    from pacelab.metrics.career import CAREERS_FILE
    if not CAREERS_FILE.exists():
        raise HTTPException(status_code=503, detail="careers not built")
    payload = json.loads(CAREERS_FILE.read_text())
    code = code.upper()
    for d in payload.get("drivers", []):
        if d.get("driver_code") == code:
            return _json_response(d)
    raise HTTPException(status_code=404, detail=f"no career for {code}")


@app.get("/api/alltime")
def alltime() -> Response:
    from pacelab.metrics.career import ALLTIME_FILE
    if not ALLTIME_FILE.exists():
        raise HTTPException(status_code=503, detail="alltime not built")
    return _json_response(json.loads(ALLTIME_FILE.read_text()))


@app.get("/api/bayes/skill")
def bayes_skill() -> Response:
    from pacelab.metrics.bayes import SKILL_FILE
    if not SKILL_FILE.exists():
        raise HTTPException(status_code=503, detail="bayesian fit not run yet. run: pacelab bayes fit")
    return _json_response(json.loads(SKILL_FILE.read_text()))


@app.get("/api/bayes/pair/{a}/{b}")
def bayes_pair(a: str, b: str) -> Response:
    from pacelab.metrics.bayes import SKILL_FILE
    if not SKILL_FILE.exists():
        raise HTTPException(status_code=503, detail="bayesian fit not run yet")
    payload = json.loads(SKILL_FILE.read_text())
    a_up = a.upper()
    b_up = b.upper()
    probs = payload.get("pairwise_probability_a_faster_than_b", {})
    if a_up not in probs or b_up not in probs.get(a_up, {}):
        raise HTTPException(status_code=404, detail=f"no posterior for {a_up} vs {b_up}")
    drivers_by_code = {d["driver_code"]: d for d in payload["drivers"]}
    return _json_response({
        "a": a_up,
        "b": b_up,
        "p_a_faster_than_b": probs[a_up][b_up],
        "a_skill": drivers_by_code.get(a_up),
        "b_skill": drivers_by_code.get(b_up),
        "seasons_used": payload.get("seasons_used"),
    })


@app.get("/api/seasons")
def seasons() -> Response:
    idx = _load_index()
    return _json_response({"seasons": idx.get("seasons", [])})


__all__ = ["app"]

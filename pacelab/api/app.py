"""FastAPI service exposing pacelab's computed driver profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
def index() -> dict[str, Any]:
    return _load_index()


@app.get("/api/drivers")
def drivers(season: int | None = None) -> dict[str, Any]:
    """List drivers, optionally restricted to a season."""
    idx = _load_index()
    drivers_list = idx.get("drivers", [])
    if season is not None:
        drivers_list = [d for d in drivers_list if d.get("season") == season]
    return {"season": season, "count": len(drivers_list), "drivers": drivers_list}


@app.get("/api/drivers/{season}/{code}")
def driver_profile(season: int, code: str) -> JSONResponse:
    path = _profile_path(season, code)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"no profile for {season}/{code}")
    return JSONResponse(content=json.loads(path.read_text()))


@app.get("/api/seasons")
def seasons() -> dict[str, Any]:
    idx = _load_index()
    return {"seasons": idx.get("seasons", [])}


__all__ = ["app"]

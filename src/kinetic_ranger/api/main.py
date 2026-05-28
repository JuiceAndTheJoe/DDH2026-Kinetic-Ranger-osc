"""FastAPI application entrypoint for Kinetic Ranger."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from dotenv import load_dotenv

from kinetic_ranger.config import load_config

from .ai_summary import router as ai_summary_router
from .recording import RecordingController
from .routes import router as rest_router
from .simulation_service import (
    LiveFrameSource,
    ReplayFrameSource,
    SimulationService,
)
from .websocket import router as ws_router

logger = logging.getLogger(__name__)

load_dotenv()

def _resolve_frontend_dist() -> Path:
    # Honor an explicit override first.
    override = os.environ.get("KR_FRONTEND_DIST")
    if override:
        return Path(override)
    # Editable / source-checkout layout: src/kinetic_ranger/api/main.py is at
    # repo_root/src/kinetic_ranger/api/main.py, so parents[3] is repo_root.
    src_layout = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if src_layout.is_dir():
        return src_layout
    # Installed-package layout (e.g. OSC's site-packages install): __file__
    # lives outside the repo, but the runtime CWD IS the repo root.
    return Path.cwd() / "frontend" / "dist"


_FRONTEND_DIST = _resolve_frontend_dist()


def _default_runs_root() -> Path:
    return Path(os.environ.get("KR_RUNS_DIR", "runs")).resolve()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    config = load_config()
    runs_root = _default_runs_root()
    runs_root.mkdir(parents=True, exist_ok=True)

    app.state.config = config
    app.state.recording = RecordingController(config, runs_root)

    replay_source = os.environ.get("KR_REPLAY_SOURCE")
    if replay_source:
        app.state.frame_source = ReplayFrameSource(config, replay_source)
        logger.info("Serving recorded run from %s", replay_source)
    else:
        # Prefer live hardware on startup; transparently fall back to synthetic.
        try:
            app.state.frame_source = LiveFrameSource(config)
            logger.info("Serving live SDR (runs dir: %s)", runs_root)
        except Exception as exc:  # pragma: no cover - depends on hardware
            logger.info(
                "Live SDR unavailable (%s); serving synthetic simulation "
                "(runs dir: %s)",
                exc,
                runs_root,
            )
            app.state.frame_source = SimulationService(config)
    yield


app = FastAPI(title="Kinetic Ranger API", version="0.1.0", lifespan=lifespan)

# Cross-origin only matters when the SPA is served from a different host
# (e.g. the Vite dev server on :5173). In single-process production deploys
# the bundle is same-origin and CORS is a no-op.
_allow_origins = [
    o.strip()
    for o in os.environ.get(
        "KR_CORS_ORIGINS", "http://localhost:5173"
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rest_router)
app.include_router(ws_router)
app.include_router(ai_summary_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if _FRONTEND_DIST.is_dir():
    # Mount the SPA last so API/WS routes win the prefix race. The
    # html=True flag makes StaticFiles serve index.html at "/", and the
    # exception handler below rewrites unknown GETs to index.html so
    # client-side routes survive a hard reload.
    app.mount(
        "/",
        StaticFiles(directory=str(_FRONTEND_DIST), html=True),
        name="spa",
    )

    @app.exception_handler(StarletteHTTPException)
    async def _spa_fallback(request, exc):  # type: ignore[no-untyped-def]
        if exc.status_code == 404 and request.method == "GET":
            accept = request.headers.get("accept", "")
            if "text/html" in accept:
                return FileResponse(_FRONTEND_DIST / "index.html")
        raise exc
else:
    logger.info(
        "frontend/dist not found at %s; SPA will not be served by FastAPI",
        _FRONTEND_DIST,
    )

"""FastAPI application entrypoint for Kinetic Ranger."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
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

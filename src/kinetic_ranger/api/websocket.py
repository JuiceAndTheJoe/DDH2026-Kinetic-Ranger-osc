"""WebSocket endpoint that streams live radar payloads at 1 Hz.

Reads ``app.state.frame_source`` on every tick so REST endpoints can swap the
underlying source (synthetic vs. recorded replay) without disconnecting clients.
Also calls ``app.state.recording.tap(frame)`` so the active stream can be
captured to disk on demand.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from fastapi.websockets import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from .simulation_service import frames_to_payload

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/radar")
async def radar_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("WebSocket client connected: %s", websocket.client)
    app = websocket.app
    try:
        while True:
            source = app.state.frame_source
            frames = await source.next_frames()
            recording = getattr(app.state, "recording", None)
            if recording is not None:
                # Record the primary (first) frame; multi-drone recording is deferred.
                recording.tap(frames[0])
            payload = frames_to_payload(frames)
            await websocket.send_text(payload.model_dump_json())
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected cleanly")
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close(code=1011)

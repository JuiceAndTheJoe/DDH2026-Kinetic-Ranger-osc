"""WebSocket endpoint that streams live radar payloads at 1 Hz."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends
from fastapi.websockets import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from .simulation_service import SimulationService

logger = logging.getLogger(__name__)
router = APIRouter()


def get_service(websocket: WebSocket) -> SimulationService:
    return websocket.app.state.simulation_service  # type: ignore[no-any-return]


@router.websocket("/ws/radar")
async def radar_stream(
    websocket: WebSocket,
    service: SimulationService = Depends(get_service),
) -> None:
    await websocket.accept()
    logger.info("WebSocket client connected: %s", websocket.client)
    try:
        while True:
            payload = await service.next_frame()
            await websocket.send_text(payload.model_dump_json())
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected cleanly")
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close(code=1011)

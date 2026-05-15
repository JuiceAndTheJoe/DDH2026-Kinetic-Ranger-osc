"""Live recording controller for the FastAPI service.

Wraps a ``RunWriter`` with start/stop/status semantics so the dashboard can
record the active WebSocket stream without changing the source.

A single instance lives on ``app.state.recording``; the WebSocket handler calls
``tap(frame)`` on every tick. When inactive, ``tap`` is a no-op.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from kinetic_ranger.logging import RunWriter, export_run

from .simulation_service import Frame

if TYPE_CHECKING:
    from kinetic_ranger.config import AppConfig


class RecordingInProgressError(RuntimeError):
    """Raised when ``start`` is called while a recording is already running."""


class NotRecordingError(RuntimeError):
    """Raised when ``stop`` is called without an active recording."""


class RecordingController:
    """Thread-safe wrapper around an optional ``RunWriter``."""

    def __init__(self, config: "AppConfig", runs_root: str | Path) -> None:
        self._config = config
        self._runs_root = Path(runs_root)
        self._runs_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._writer: RunWriter | None = None
        self._started_at_s: float | None = None
        self._tick_count: int = 0
        self._run_id: str | None = None

    @property
    def runs_root(self) -> Path:
        return self._runs_root

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._writer is not None

    def status(self) -> dict:
        with self._lock:
            return {
                "recording": self._writer is not None,
                "run_id": self._run_id,
                "started_at_s": self._started_at_s,
                "tick_count": self._tick_count,
            }

    def start(self, mode_label: str = "dashboard") -> dict:
        with self._lock:
            if self._writer is not None:
                raise RecordingInProgressError(
                    f"recording already in progress: {self._run_id}"
                )
            self._writer = RunWriter(self._runs_root, mode_label, self._config)
            self._started_at_s = time.time()
            self._tick_count = 0
            self._run_id = self._writer.path.name
            return {
                "run_id": self._run_id,
                "started_at_s": self._started_at_s,
            }

    def tap(self, frame: Frame) -> None:
        """Persist this frame if a recording is active. No-op otherwise."""
        with self._lock:
            writer = self._writer
            if writer is None:
                return
            writer.log_snapshot(
                frame.observation, frame.estimate, frame.alert, frame.telemetry,
                range_m=frame.range_m,
            )
            self._tick_count += 1

    def stop(self) -> dict:
        with self._lock:
            writer = self._writer
            if writer is None:
                raise NotRecordingError("no recording in progress")
            run_path = writer.path
            tick_count = self._tick_count
            started_at_s = self._started_at_s or time.time()
            writer.close()
            self._writer = None
            self._run_id = None
            self._started_at_s = None
            self._tick_count = 0

        # Outside the lock: export CSVs so the runs list can show severity bars.
        try:
            export_run(run_path)
        except Exception:  # pragma: no cover - best-effort
            pass

        return {
            "run_id": run_path.name,
            "tick_count": tick_count,
            "duration_s": max(0.0, time.time() - started_at_s),
            "path": str(run_path),
        }

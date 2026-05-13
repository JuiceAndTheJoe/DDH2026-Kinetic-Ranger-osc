"""Owns a run directory: manifest.json + snapshots.jsonl."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from kinetic_ranger.logging.session_logger import SessionLogger
from kinetic_ranger.models import (
    AlertDecision,
    RadioObservation,
    TelemetrySample,
    ThreatEstimate,
)

if TYPE_CHECKING:
    from kinetic_ranger.config import AppConfig

SCHEMA_VERSION = 1
SNAPSHOTS_FILENAME = "snapshots.jsonl"
MANIFEST_FILENAME = "manifest.json"


def _hash_config(config: "AppConfig") -> str:
    payload = json.dumps(
        {
            "radio": asdict(config.radio),
            "telemetry": asdict(config.telemetry),
            "estimator": asdict(config.estimator),
            "alert": asdict(config.alert),
            "simulation": asdict(config.simulation),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class RunWriter:
    """A run directory: snapshots.jsonl streamed to disk, manifest.json on close."""

    def __init__(
        self,
        root_dir: str | Path,
        mode: str,
        config: "AppConfig",
    ) -> None:
        self.mode = mode
        self.started_at_s = time.time()
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(self.started_at_s))
        self.path = Path(root_dir) / f"{stamp}_{mode}"
        self.path.mkdir(parents=True, exist_ok=True)
        self._session_logger = SessionLogger(self.path, filename=SNAPSHOTS_FILENAME)
        self._tick_count = 0
        self._first_timestamp_s: float | None = None
        self._last_timestamp_s: float | None = None
        self._config_hash = _hash_config(config)

    def log_snapshot(
        self,
        observation: RadioObservation,
        estimate: ThreatEstimate,
        alert: AlertDecision,
        telemetry: TelemetrySample | None = None,
    ) -> None:
        self._session_logger.log_snapshot(observation, estimate, alert, telemetry)
        if self._first_timestamp_s is None:
            self._first_timestamp_s = observation.timestamp_s
        self._last_timestamp_s = observation.timestamp_s
        self._tick_count += 1

    def close(self) -> None:
        self._session_logger.close()
        duration_s = 0.0
        if self._first_timestamp_s is not None and self._last_timestamp_s is not None:
            duration_s = self._last_timestamp_s - self._first_timestamp_s
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "mode": self.mode,
            "started_at_s": self.started_at_s,
            "duration_s": duration_s,
            "tick_count": self._tick_count,
            "config_hash": self._config_hash,
        }
        (self.path / MANIFEST_FILENAME).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

    def __enter__(self) -> "RunWriter":
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        self.close()

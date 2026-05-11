from __future__ import annotations

import json
import time
from pathlib import Path

from kinetic_ranger.models import AlertDecision, RadioObservation, TelemetrySample, ThreatEstimate


class SessionLogger:
    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        filename = f"session-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
        self.path = self.root_dir / filename
        self._handle = self.path.open("w", encoding="utf-8")

    def log_snapshot(
        self,
        observation: RadioObservation,
        estimate: ThreatEstimate,
        alert: AlertDecision,
        telemetry: TelemetrySample | None = None,
    ) -> None:
        payload = {
            "observation": observation.to_dict(),
            "estimate": estimate.to_dict(),
            "alert": alert.to_dict(),
            "telemetry": telemetry.to_dict() if telemetry else None,
        }
        self._handle.write(json.dumps(payload) + "\n")
        self._handle.flush()

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.close()

    def __enter__(self) -> "SessionLogger":
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        self.close()

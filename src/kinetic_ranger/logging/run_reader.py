"""Parses a run directory written by RunWriter."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from kinetic_ranger.models import (
    AlertDecision,
    RadioObservation,
    TelemetrySample,
    ThreatEstimate,
)

SUPPORTED_SCHEMA_VERSION = 1


class RunReader:
    """Read manifest.json + snapshots.jsonl from a run directory."""

    def __init__(self, run_dir: str | Path) -> None:
        self.path = Path(run_dir)
        manifest_path = self.path / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"Not a run directory (no manifest.json): {self.path}"
            )
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        version = int(self.manifest.get("schema_version", 0))
        if version != SUPPORTED_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported run schema_version={version} (expected {SUPPORTED_SCHEMA_VERSION})"
            )

    def iter_snapshots(
        self,
    ) -> Iterator[
        tuple[RadioObservation, ThreatEstimate, AlertDecision, TelemetrySample | None]
    ]:
        snapshots_path = self.path / "snapshots.jsonl"
        with snapshots_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                observation = RadioObservation(**row["observation"])
                estimate_payload = dict(row["estimate"])
                cov = estimate_payload.get("covariance_diag")
                if isinstance(cov, list):
                    estimate_payload["covariance_diag"] = tuple(cov)
                estimate = ThreatEstimate(**estimate_payload)
                alert = AlertDecision(**row["alert"])
                telemetry_payload = row.get("telemetry")
                telemetry = (
                    TelemetrySample(**telemetry_payload) if telemetry_payload else None
                )
                yield observation, estimate, alert, telemetry

    def iter_observations(
        self,
    ) -> Iterator[tuple[RadioObservation, TelemetrySample | None]]:
        for observation, _estimate, _alert, telemetry in self.iter_snapshots():
            yield observation, telemetry

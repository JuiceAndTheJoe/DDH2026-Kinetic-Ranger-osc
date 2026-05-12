"""Bridges the synchronous core simulation to the async WebSocket loop.

Runs SimulatedApproachCapture → extract_observation → EKF → AlertRuleEngine
in a continuous loop, resetting all stateful components when each 30-step
batch is exhausted. Uses run_in_executor for the FFT-heavy extract_observation.
"""
from __future__ import annotations

import asyncio
import logging
import math

from kinetic_ranger.alerting.rules import AlertRuleEngine
from kinetic_ranger.config import AppConfig
from kinetic_ranger.estimation.ekf import ClosingThreatEKF
from kinetic_ranger.models import IQWindow
from kinetic_ranger.radio.capture import SimulatedApproachCapture
from kinetic_ranger.radio.features import extract_observation

from .schemas import PayloadSummary, RadarPayload, ReceiverInfo, TargetDisplay, TargetState

logger = logging.getLogger(__name__)

_SEVERITY_TO_THREAT: dict[str, str] = {
    "critical": "CRITICAL",
    "warning": "HIGH",
    "info": "LOW",
}

_RECEIVER = ReceiverInfo(id="station-1", label="Passive RF Sensor")


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _generate_windows(config: AppConfig) -> list[IQWindow]:
    return SimulatedApproachCapture(config.radio, config.simulation).iter_windows()


class SimulationService:
    """Stateful simulation runner shared across all WebSocket clients.

    All connected clients see the same frame at the same time, matching
    the semantics of a real shared RF sensor.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._windows: list[IQWindow] = _generate_windows(config)
        self._index: int = 0
        self._loop_count: int = 0
        self._ekf = ClosingThreatEKF(config.estimator)
        self._alert_engine = AlertRuleEngine(config.alert)
        self._prev_rssi: float | None = None

        steps = config.simulation.steps
        dt = config.simulation.dt_s
        self._loop_duration_s: float = steps * dt  # seconds of sim time per batch

    def _reset_loop(self, new_windows: list[IQWindow]) -> None:
        """Reset stateful components for the next simulation loop."""
        self._loop_count += 1
        self._index = 0
        # Fresh instances avoid stale last_timestamp_s and alert state carry-over.
        self._ekf = ClosingThreatEKF(self._config.estimator)
        self._alert_engine = AlertRuleEngine(self._config.alert)
        self._prev_rssi = None
        self._windows = new_windows

    async def next_frame(self) -> RadarPayload:
        loop = asyncio.get_event_loop()

        if self._index >= len(self._windows):
            new_windows = await loop.run_in_executor(
                None, _generate_windows, self._config
            )
            self._reset_loop(new_windows)

        window = self._windows[self._index]
        self._index += 1

        # FFT inside extract_observation — offload to thread pool.
        obs = await loop.run_in_executor(None, extract_observation, window)

        estimate = self._ekf.step(obs)
        alert = self._alert_engine.evaluate(estimate, obs)

        # Monotonic wall-clock time across loop resets.
        time_s = self._loop_count * self._loop_duration_s + window.timestamp_s

        # RSSI slope: dB/s. Zero on the first frame of each loop.
        dt_s = self._config.simulation.dt_s
        rssi_slope = (
            (obs.rssi_dbfs - self._prev_rssi) / dt_s
            if self._prev_rssi is not None
            else 0.0
        )
        self._prev_rssi = obs.rssi_dbfs

        # Map AlertDecision.severity (lowercase) to the payload's threat vocabulary.
        threat_level = _SEVERITY_TO_THREAT.get(alert.severity, "LOW")
        if not alert.active:
            threat_level = "NONE"

        ttc = estimate.time_to_impact_s
        estimated_ttc_s = ttc if ttc is not None else -1.0
        closing = estimate.closing_rate_mps < -0.1

        # Slowly rotate the bearing across loops for visual interest on the radar.
        bearing_deg = float((self._loop_count * 30 + self._index * 3) % 360)

        # Normalised proximity: 0 = far/unknown, 1 = impact now.
        tti_threshold = self._config.alert.tti_threshold_s
        if ttc is not None:
            radial_ttc_norm = _clamp(1.0 - ttc / max(tti_threshold, 1.0), 0.0, 1.0)
        else:
            radial_ttc_norm = 0.0

        target = TargetState(
            id="drone-1",
            rssi_db=round(obs.rssi_dbfs, 2),
            rssi_slope_db_s=round(rssi_slope, 3),
            estimated_ttc_s=round(estimated_ttc_s, 2),
            confidence=round(_clamp(estimate.confidence, 0.0, 1.0), 3),
            threat_level=threat_level,
            closing=closing,
            display=TargetDisplay(
                bearing_deg=round(bearing_deg, 1),
                radial_ttc_norm=round(radial_ttc_norm, 3),
            ),
        )

        return RadarPayload(
            mode="simulation",
            time_s=round(time_s, 2),
            receiver=_RECEIVER,
            targets=[target],
            summary=PayloadSummary(
                highest_threat=threat_level,
                active_targets=1 if alert.active else 0,
                alert=alert.active,
            ),
        )

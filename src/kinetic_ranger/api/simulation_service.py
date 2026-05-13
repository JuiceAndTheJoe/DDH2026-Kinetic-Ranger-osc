"""Frame sources for the /ws/radar stream.

Two implementations:

- ``SimulationService`` — drives the EKF + alerting pipeline off the synthetic
  ``SimulatedApproachCapture``. Reused for every connected client.
- ``ReplayFrameSource`` — drives the same pipeline from a recorded run directory
  written by ``RunWriter``. Supports pause + seek so the dashboard can scrub
  through a recording.

Both expose ``async def next_frame() -> Frame``. ``frame_to_payload`` then
converts to the wire-shaped ``RadarPayload``. This split lets the recording
controller see the rich per-tick data without re-running the pipeline.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from kinetic_ranger.alerting.rules import AlertRuleEngine
from kinetic_ranger.config import AppConfig
from kinetic_ranger.estimation.ekf import ClosingThreatEKF
from kinetic_ranger.logging import RunReader
from kinetic_ranger.models import (
    AlertDecision,
    IQWindow,
    RadioObservation,
    TelemetrySample,
    ThreatEstimate,
)
from kinetic_ranger.radio.capture import AntSdrIioCapture, SimulatedApproachCapture
from kinetic_ranger.radio.features import extract_observation

from .schemas import (
    Mode,
    PayloadSummary,
    RadarPayload,
    ReceiverInfo,
    TargetDisplay,
    TargetState,
)

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


@dataclass(slots=True)
class Frame:
    """Rich per-tick state. The wire payload is a projection of this."""

    observation: RadioObservation
    estimate: ThreatEstimate
    alert: AlertDecision
    telemetry: TelemetrySample | None
    mode: Mode
    target_id: str
    time_s: float
    rssi_slope_db_s: float
    bearing_deg: float
    tti_threshold_s: float
    source_run_id: str | None = None
    replay_index: int | None = None
    replay_tick_count: int | None = None
    paused: bool = False


def frame_to_payload(frame: Frame) -> RadarPayload:
    obs = frame.observation
    estimate = frame.estimate
    alert = frame.alert

    threat_level = _SEVERITY_TO_THREAT.get(alert.severity, "LOW")
    if not alert.active:
        threat_level = "NONE"

    ttc = estimate.time_to_impact_s
    estimated_ttc_s = ttc if ttc is not None else -1.0
    closing = estimate.closing_rate_mps < -0.1
    if ttc is not None:
        radial_ttc_norm = _clamp(1.0 - ttc / max(frame.tti_threshold_s, 1.0), 0.0, 1.0)
    else:
        radial_ttc_norm = 0.0

    target = TargetState(
        id=frame.target_id,
        rssi_db=round(obs.rssi_dbfs, 2),
        rssi_slope_db_s=round(frame.rssi_slope_db_s, 3),
        estimated_ttc_s=round(estimated_ttc_s, 2),
        # Absolute range is unobservable without a known Tx power. Send the
        # -1.0 sentinel (same convention as estimated_ttc_s) so the wire
        # schema stays stable; the frontend should treat negative values as
        # "unknown" rather than a position.
        range_m=-1.0,
        confidence=round(_clamp(estimate.confidence, 0.0, 1.0), 3),
        threat_level=threat_level,
        closing=closing,
        display=TargetDisplay(
            bearing_deg=round(frame.bearing_deg, 1),
            radial_ttc_norm=round(radial_ttc_norm, 3),
        ),
    )

    return RadarPayload(
        mode=frame.mode,
        time_s=round(frame.time_s, 2),
        receiver=_RECEIVER,
        targets=[target],
        summary=PayloadSummary(
            highest_threat=threat_level,
            active_targets=1 if alert.active else 0,
            alert=alert.active,
        ),
        source_run_id=frame.source_run_id,
        replay_index=frame.replay_index,
        replay_tick_count=frame.replay_tick_count,
        paused=frame.paused,
    )


class FrameSource(Protocol):
    async def next_frame(self) -> Frame: ...


class SimulationService:
    """Synthetic-source pipeline shared across all WebSocket clients."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._windows: list[IQWindow] = _generate_windows(config)
        self._index: int = 0
        self._loop_count: int = 0
        self._ekf = ClosingThreatEKF(config.estimator)
        self._alert_engine = AlertRuleEngine(config.alert)

        steps = config.simulation.steps
        dt = config.simulation.dt_s
        self._loop_duration_s: float = steps * dt
        self.paused: bool = False
        self._last_frame: Frame | None = None

    def _reset_loop(self, new_windows: list[IQWindow]) -> None:
        self._loop_count += 1
        self._index = 0
        self._ekf = ClosingThreatEKF(self._config.estimator)
        self._alert_engine = AlertRuleEngine(self._config.alert)
        self._windows = new_windows

    async def next_frame(self) -> Frame:
        if self.paused and self._last_frame is not None:
            self._last_frame.paused = True
            return self._last_frame

        loop = asyncio.get_event_loop()

        if self._index >= len(self._windows):
            new_windows = await loop.run_in_executor(
                None, _generate_windows, self._config
            )
            self._reset_loop(new_windows)

        window = self._windows[self._index]
        self._index += 1

        obs = await loop.run_in_executor(None, extract_observation, window)
        estimate = self._ekf.step(obs)
        alert = self._alert_engine.evaluate(estimate, obs)

        time_s = self._loop_count * self._loop_duration_s + window.timestamp_s

        # RSSI slope (dB/s) comes from the EKF state — it is the primary
        # observable now that Tx power is treated as unknown.
        rssi_slope = estimate.rssi_slope_db_per_s

        bearing_deg = float((self._loop_count * 30 + self._index * 3) % 360)

        frame = Frame(
            observation=obs,
            estimate=estimate,
            alert=alert,
            telemetry=None,
            mode="simulation",
            target_id="drone-1",
            time_s=time_s,
            rssi_slope_db_s=rssi_slope,
            bearing_deg=bearing_deg,
            tti_threshold_s=self._config.alert.tti_threshold_s,
        )
        self._last_frame = frame
        return frame


class LiveFrameSource:
    """Drives /ws/radar from a live SDR via ``AntSdrIioCapture``.

    Construction probes the device — if ``pyadi-iio`` is not installed or the
    radio is not reachable, the constructor raises and the caller should fall
    back to a synthetic source.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        # AntSdrIioCapture.__init__ both checks pyadi-iio is importable AND
        # opens a connection to the device. Any failure surfaces here.
        self._capture = AntSdrIioCapture(config.radio)
        self._ekf = ClosingThreatEKF(config.estimator)
        self._alert_engine = AlertRuleEngine(config.alert)
        self._tick_index: int = 0

    async def next_frame(self) -> Frame:
        loop = asyncio.get_event_loop()
        window = await loop.run_in_executor(None, self._capture.read_window)
        agc_enabled = self._config.radio.gain_mode != "manual"
        obs = await loop.run_in_executor(
            None, extract_observation, window, agc_enabled
        )
        estimate = self._ekf.step(obs)
        alert = self._alert_engine.evaluate(estimate, obs)

        rssi_slope = estimate.rssi_slope_db_per_s

        self._tick_index += 1
        bearing_deg = float((self._tick_index * 3) % 360)

        return Frame(
            observation=obs,
            estimate=estimate,
            alert=alert,
            telemetry=None,
            mode="live",
            target_id="live-1",
            time_s=window.timestamp_s,
            rssi_slope_db_s=rssi_slope,
            bearing_deg=bearing_deg,
            tti_threshold_s=self._config.alert.tti_threshold_s,
        )


class ReplayFrameSource:
    """Drives /ws/radar from a recorded run directory.

    Re-runs the EKF + alerting pipeline against the stored observations.
    Supports pause + seek so the dashboard can scrub through a recording.
    When the run is exhausted the source loops, resetting estimator state.
    """

    def __init__(self, config: AppConfig, run_dir: str | Path) -> None:
        self._config = config
        self._run_dir = Path(run_dir)
        self.run_id = self._run_dir.name
        reader = RunReader(self._run_dir)
        self._observations: list[tuple[RadioObservation, TelemetrySample | None]] = (
            list(reader.iter_observations())
        )
        if not self._observations:
            raise ValueError(f"Replay source has no observations: {self._run_dir}")
        self._index: int = 0
        self._loop_count: int = 0
        self._ekf = ClosingThreatEKF(config.estimator)
        self._alert_engine = AlertRuleEngine(config.alert)
        self._last_frame: Frame | None = None
        self.paused: bool = False

        first_t = self._observations[0][0].timestamp_s
        last_t = self._observations[-1][0].timestamp_s
        self._loop_duration_s: float = max(last_t - first_t, 0.0) + config.simulation.dt_s

    @property
    def tick_count(self) -> int:
        return len(self._observations)

    @property
    def current_index(self) -> int:
        # _index points at the NEXT frame to emit; the most recent emitted
        # frame was at _index - 1 (clamped to 0).
        return max(0, self._index - 1)

    def _reset_pipeline(self) -> None:
        self._ekf = ClosingThreatEKF(self._config.estimator)
        self._alert_engine = AlertRuleEngine(self._config.alert)

    def _reset_loop(self) -> None:
        self._loop_count += 1
        self._index = 0
        self._reset_pipeline()

    def _emit_at(self, index: int) -> Frame:
        observation, telemetry = self._observations[index]
        estimate = self._ekf.step(observation, telemetry)
        alert = self._alert_engine.evaluate(estimate, observation)

        time_s = self._loop_count * self._loop_duration_s + observation.timestamp_s

        rssi_slope = estimate.rssi_slope_db_per_s

        bearing_deg = float((self._loop_count * 30 + (index + 1) * 3) % 360)

        frame = Frame(
            observation=observation,
            estimate=estimate,
            alert=alert,
            telemetry=telemetry,
            mode="replay",
            target_id="recorded-1",
            time_s=time_s,
            rssi_slope_db_s=rssi_slope,
            bearing_deg=bearing_deg,
            tti_threshold_s=self._config.alert.tti_threshold_s,
            source_run_id=self.run_id,
            replay_index=index,
            replay_tick_count=self.tick_count,
            paused=self.paused,
        )
        self._last_frame = frame
        return frame

    def seek(self, target_index: int) -> Frame:
        """Jump to ``target_index`` and rebuild EKF state from frame 0."""
        target_index = max(0, min(target_index, self.tick_count - 1))
        self._reset_pipeline()
        self._index = 0
        for i in range(target_index):
            self._emit_at(i)
            self._index = i + 1
        frame = self._emit_at(target_index)
        self._index = target_index + 1
        return frame

    async def next_frame(self) -> Frame:
        if self.paused and self._last_frame is not None:
            # Update the cached frame's `paused` flag so the wire reflects state.
            self._last_frame.paused = True
            return self._last_frame

        if self._index >= self.tick_count:
            self._reset_loop()

        frame = self._emit_at(self._index)
        self._index += 1
        return frame

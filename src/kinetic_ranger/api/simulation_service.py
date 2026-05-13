"""Frame sources for the /ws/radar stream.

Three implementations:

- ``SimulationService`` — drives N independent EKF + alerting pipelines off
  synthetic ``SimulatedApproachCapture`` sequences (one per simulated drone).
  Reused for every connected client.
- ``LiveFrameSource`` — drives the pipeline from a live SDR via AntSdrIioCapture.
- ``ReplayFrameSource`` — drives the pipeline from a recorded run directory.
  Supports pause + seek so the dashboard can scrub through a recording.

All three expose ``async def next_frames() -> list[Frame]``.
``frames_to_payload`` converts the list to the wire-shaped ``RadarPayload``.
This split lets the recording controller see the rich per-tick data without
re-running the pipeline.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from kinetic_ranger.alerting.rules import AlertRuleEngine
from kinetic_ranger.config import AppConfig, RadioConfig, SimulationConfig
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

# Threat ordering used for summary aggregation across multiple targets.
_THREAT_RANK: dict[str, int] = {"NONE": 0, "LOW": 1, "HIGH": 2, "CRITICAL": 3}

_RECEIVER = ReceiverInfo(id="station-1", label="Passive RF Sensor")

# Per-drone start-range multipliers so each simulated drone has a slightly
# different approach timeline. Index cycles for drone_count > 10.
_RANGE_MULTIPLIERS = [1.0, 0.80, 1.20, 0.65, 1.35, 0.55, 1.50, 0.45, 1.65, 0.40]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _generate_windows(radio: RadioConfig, sim: SimulationConfig) -> list[IQWindow]:
    return SimulatedApproachCapture(radio, sim).iter_windows()


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
    # Simulation truth metadata — not RF-estimated. None for live/replay sources.
    altitude_m: float | None = None


# ---------------------------------------------------------------------------
# Payload conversion helpers
# ---------------------------------------------------------------------------


def _frame_to_target_state(frame: Frame) -> TargetState:
    """Convert one Frame to its wire TargetState representation."""
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

    return TargetState(
        id=frame.target_id,
        rssi_db=round(obs.rssi_dbfs, 2),
        rssi_slope_db_s=round(frame.rssi_slope_db_s, 3),
        estimated_ttc_s=round(estimated_ttc_s, 2),
        # Absolute range is unobservable without a known Tx power. Send the
        # -1.0 sentinel; frontend treats negative values as "unknown".
        range_m=-1.0,
        confidence=round(_clamp(estimate.confidence, 0.0, 1.0), 3),
        threat_level=threat_level,
        closing=closing,
        display=TargetDisplay(
            bearing_deg=round(frame.bearing_deg, 1),
            radial_ttc_norm=round(radial_ttc_norm, 3),
        ),
        altitude_m=frame.altitude_m,
    )


def frames_to_payload(frames: list[Frame]) -> RadarPayload:
    """Convert one or more Frames into a single RadarPayload.

    For single-frame sources (live, replay) frames has one element.
    For multi-drone simulation, one Frame per active drone.
    """
    targets = [_frame_to_target_state(f) for f in frames]

    highest = max(targets, key=lambda t: _THREAT_RANK.get(t.threat_level, 0))
    active_count = sum(1 for f in frames if f.alert.active)
    any_alert = any(f.alert.active for f in frames)

    primary = frames[0]
    return RadarPayload(
        mode=primary.mode,
        time_s=round(primary.time_s, 2),
        receiver=_RECEIVER,
        targets=targets,
        summary=PayloadSummary(
            highest_threat=highest.threat_level,
            active_targets=active_count,
            alert=any_alert,
        ),
        source_run_id=primary.source_run_id,
        replay_index=primary.replay_index,
        replay_tick_count=primary.replay_tick_count,
        paused=primary.paused,
    )


def frame_to_payload(frame: Frame) -> RadarPayload:
    """Backward-compat wrapper — delegates to frames_to_payload."""
    return frames_to_payload([frame])


# ---------------------------------------------------------------------------
# FrameSource protocol
# ---------------------------------------------------------------------------


class FrameSource(Protocol):
    async def next_frames(self) -> list[Frame]: ...


# ---------------------------------------------------------------------------
# Per-drone state (used by SimulationService only)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _DroneState:
    drone_index: int        # 0-based; used to reproduce perturbation on reset
    target_id: str          # "drone-1", "drone-2", ...
    windows: list[IQWindow]
    index: int              # index of next window to consume
    loop_count: int
    ekf: ClosingThreatEKF
    alert_engine: AlertRuleEngine
    bearing_base_deg: float  # evenly-distributed compass bearing for this drone
    loop_duration_s: float
    altitude_m: float        # stored for future display / GPS validation


# ---------------------------------------------------------------------------
# SimulationService — multi-drone synthetic source
# ---------------------------------------------------------------------------


class SimulationService:
    """Synthetic multi-drone pipeline shared across all WebSocket clients."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        n = max(1, min(10, config.simulation.drone_count))
        self._drones: list[_DroneState] = [self._make_drone(i, n) for i in range(n)]
        self.paused: bool = False
        self._last_frames: list[Frame] | None = None

    def _make_sim_config(self, drone_index: int) -> SimulationConfig:
        """Return a SimulationConfig with per-drone range offset and speed-derived steps."""
        base = self._config.simulation
        mult = _RANGE_MULTIPLIERS[drone_index % len(_RANGE_MULTIPLIERS)]
        perturbed_start = base.start_range_m * mult
        # TODO: use base.scenario ("flyby", "hover") to change the range profile here
        # instead of a straight linear approach. For now only "direct_approach" is implemented.
        # Derive the number of steps so the drone closes at speed_mps.
        # Each step advances dt_s seconds; range closes by speed_mps * dt_s per step.
        total_range = max(perturbed_start - base.end_range_m, 1.0)
        steps = max(5, int(round(total_range / (max(base.speed_mps, 0.1) * base.dt_s))))
        return SimulationConfig(
            steps=steps,
            dt_s=base.dt_s,
            start_range_m=perturbed_start,
            end_range_m=base.end_range_m,
            effective_power_db=base.effective_power_db,
            path_loss_exponent=base.path_loss_exponent,
            noise_std=base.noise_std,
            drone_count=base.drone_count,
            speed_mps=base.speed_mps,
            altitude_m=base.altitude_m,
            scenario=base.scenario,
            bursty=base.bursty,
        )

    def _make_drone(self, i: int, total: int) -> _DroneState:
        sim_cfg = self._make_sim_config(i)
        windows = _generate_windows(self._config.radio, sim_cfg)
        bearing_base = (i * 360.0 / total) % 360.0
        return _DroneState(
            drone_index=i,
            target_id=f"drone-{i + 1}",
            windows=windows,
            index=0,
            loop_count=0,
            ekf=ClosingThreatEKF(self._config.estimator),
            alert_engine=AlertRuleEngine(self._config.alert),
            bearing_base_deg=bearing_base,
            loop_duration_s=len(windows) * self._config.simulation.dt_s,
            altitude_m=self._config.simulation.altitude_m,
        )

    async def next_frames(self) -> list[Frame]:
        if self.paused and self._last_frames is not None:
            for f in self._last_frames:
                f.paused = True
            return self._last_frames

        loop = asyncio.get_event_loop()
        frames: list[Frame] = []

        for drone in self._drones:
            if drone.index >= len(drone.windows):
                sim_cfg = self._make_sim_config(drone.drone_index)
                new_windows = await loop.run_in_executor(
                    None, _generate_windows, self._config.radio, sim_cfg
                )
                drone.loop_count += 1
                drone.index = 0
                drone.ekf = ClosingThreatEKF(self._config.estimator)
                drone.alert_engine = AlertRuleEngine(self._config.alert)
                drone.windows = new_windows

            window = drone.windows[drone.index]
            drone.index += 1

            obs = await loop.run_in_executor(None, extract_observation, window)
            estimate = drone.ekf.step(obs)
            alert = drone.alert_engine.evaluate(estimate, obs)

            time_s = drone.loop_count * drone.loop_duration_s + window.timestamp_s
            rssi_slope = estimate.rssi_slope_db_per_s
            # Small per-tick bearing drift keeps the blip from being perfectly static.
            bearing_deg = (drone.bearing_base_deg + drone.index * 0.5) % 360.0

            frames.append(Frame(
                observation=obs,
                estimate=estimate,
                alert=alert,
                telemetry=None,
                mode="simulation",
                target_id=drone.target_id,
                time_s=time_s,
                rssi_slope_db_s=rssi_slope,
                bearing_deg=bearing_deg,
                tti_threshold_s=self._config.alert.tti_threshold_s,
                altitude_m=drone.altitude_m,
            ))

        self._last_frames = frames
        return frames


# ---------------------------------------------------------------------------
# LiveFrameSource — hardware-backed SDR source
# ---------------------------------------------------------------------------


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

    async def next_frames(self) -> list[Frame]:
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

        return [Frame(
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
        )]


# ---------------------------------------------------------------------------
# ReplayFrameSource — recorded-run replay source
# ---------------------------------------------------------------------------


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

    async def next_frames(self) -> list[Frame]:
        if self.paused and self._last_frame is not None:
            # Update the cached frame's `paused` flag so the wire reflects state.
            self._last_frame.paused = True
            return [self._last_frame]

        if self._index >= self.tick_count:
            self._reset_loop()

        frame = self._emit_at(self._index)
        self._index += 1
        return [frame]

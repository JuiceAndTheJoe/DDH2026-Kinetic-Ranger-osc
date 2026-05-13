"""Pydantic models for the WebSocket payload contract and REST responses.

These are the wire types only — no imports from kinetic_ranger core.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Mode = Literal["simulation", "replay", "live"]


class ReceiverInfo(BaseModel):
    id: str
    label: str


class TargetDisplay(BaseModel):
    bearing_deg: float
    radial_ttc_norm: float  # 0.0 = far/unknown, 1.0 = impact imminent


class TargetState(BaseModel):
    id: str
    rssi_db: float
    rssi_slope_db_s: float
    estimated_ttc_s: float  # -1.0 sentinel when time-to-contact is unavailable
    range_m: float          # EKF range state in meters
    confidence: float
    threat_level: str       # "CRITICAL" | "HIGH" | "LOW" | "NONE"
    closing: bool
    display: TargetDisplay


class PayloadSummary(BaseModel):
    highest_threat: str
    active_targets: int
    alert: bool


class RadarPayload(BaseModel):
    mode: Mode
    time_s: float
    receiver: ReceiverInfo
    targets: list[TargetState]
    summary: PayloadSummary
    source_run_id: str | None = None
    replay_index: int | None = None
    replay_tick_count: int | None = None
    paused: bool = False


class RunSummary(BaseModel):
    run_id: str
    mode: str
    started_at_s: float
    duration_s: float
    tick_count: int
    peak_severity: str  # "critical" | "warning" | "info" | "none"


class TimelinePoint(BaseModel):
    frame: int
    time_s: float
    threat_level: str
    alert_active: bool


class RecordingStatus(BaseModel):
    recording: bool
    run_id: str | None = None
    started_at_s: float | None = None
    tick_count: int = 0


class RecordingStartResponse(BaseModel):
    run_id: str
    started_at_s: float


class RecordingStopResponse(BaseModel):
    run_id: str
    tick_count: int
    duration_s: float
    path: str


class SourceState(BaseModel):
    mode: Mode
    source_run_id: str | None = None
    replay_index: int | None = None
    replay_tick_count: int | None = None
    paused: bool = False


class SeekRequest(BaseModel):
    frame: int


class SimulationControlRequest(BaseModel):
    action: Literal["start", "pause", "reset"]


class SimulationConfigRequest(BaseModel):
    start_range_m: float | None = None
    end_range_m: float | None = None
    noise_std: float | None = None
    steps: int | None = None
    dt_s: float | None = None
    # Future fields — accepted in schema, not yet applied to backend config
    drone_count: int | None = None
    speed_mps: float | None = None
    altitude_m: float | None = None


class SimulationStatus(BaseModel):
    paused: bool
    drone_count: int
    start_range_m: float
    end_range_m: float
    noise_std: float
    steps: int
    dt_s: float

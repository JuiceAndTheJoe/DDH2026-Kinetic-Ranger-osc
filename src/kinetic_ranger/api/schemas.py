"""Pydantic models for the WebSocket payload contract.

These are the wire types only — no imports from kinetic_ranger core.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


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
    confidence: float
    threat_level: str       # "CRITICAL" | "HIGH" | "LOW" | "NONE"
    closing: bool
    display: TargetDisplay


class PayloadSummary(BaseModel):
    highest_threat: str
    active_targets: int
    alert: bool


class RadarPayload(BaseModel):
    mode: Literal["simulation"]
    time_s: float
    receiver: ReceiverInfo
    targets: list[TargetState]
    summary: PayloadSummary

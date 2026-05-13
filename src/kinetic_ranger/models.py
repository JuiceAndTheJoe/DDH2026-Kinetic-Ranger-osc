from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


@dataclass(slots=True)
class IQWindow:
    """A timestamped block of complex IQ samples."""

    samples: np.ndarray
    sample_rate_hz: float
    center_frequency_hz: float
    timestamp_s: float


@dataclass(slots=True)
class RadioObservation:
    """Features extracted from one IQ processing window."""

    timestamp_s: float
    center_frequency_hz: float
    rssi_dbfs: float
    cfo_hz: float
    snr_db: float
    confidence: float
    noise_floor_dbfs: float | None = None
    agc_enabled: bool = False
    spectral_width_hz: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TelemetrySample:
    """A motion sample aligned to the estimator timeline."""

    timestamp_s: float
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    ground_speed_mps: float
    heading_deg: float
    local_east_m: float
    local_north_m: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ThreatEstimate:
    """Current estimator state and confidence.

    Tx power and absolute range are unobservable from RSSI alone, so the
    estimator tracks observable quantities only: smoothed RSSI level,
    RSSI temporal slope (dB/s), and Doppler-derived closing rate.
    """

    timestamp_s: float
    rssi_dbfs: float
    rssi_slope_db_per_s: float
    closing_rate_mps: float
    time_to_impact_s: float | None
    covariance_diag: tuple[float, float, float]
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AlertDecision:
    """Decision emitted by the alerting layer."""

    timestamp_s: float
    active: bool
    severity: str
    reason: str
    sustained_hits: int
    cooldown_remaining_s: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

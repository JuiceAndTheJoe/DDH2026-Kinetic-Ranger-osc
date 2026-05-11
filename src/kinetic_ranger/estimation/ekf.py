from __future__ import annotations

import math

import numpy as np

from kinetic_ranger.config import EstimatorConfig
from kinetic_ranger.models import RadioObservation, TelemetrySample, ThreatEstimate

SPEED_OF_LIGHT_MPS = 299_792_458.0


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


class ClosingThreatEKF:
    """Small EKF for range, closing rate, and effective power."""

    def __init__(self, config: EstimatorConfig) -> None:
        self.config = config
        self.state = np.array(
            [
                config.initial_range_m,
                config.initial_closing_rate_mps,
                config.initial_effective_power_db,
            ],
            dtype=float,
        )
        self.covariance = np.diag(config.initial_covariance_diag)
        self.last_timestamp_s: float | None = None

    def predict(self, dt_s: float) -> None:
        transition = np.array(
            [
                [1.0, dt_s, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        )
        process_noise = np.diag(self.config.process_noise_diag) * max(dt_s, 1e-3)
        self.state = transition @ self.state
        self.state[0] = max(self.state[0], self.config.minimum_range_m)
        self.covariance = transition @ self.covariance @ transition.T + process_noise

    def _measurement_model(self) -> np.ndarray:
        range_m = max(self.state[0], self.config.minimum_range_m)
        closing_rate_mps = self.state[1]
        effective_power_db = self.state[2]

        rssi_dbfs = effective_power_db - 10.0 * self.config.path_loss_exponent * math.log10(range_m)
        cfo_hz = -(self.config.carrier_frequency_hz / SPEED_OF_LIGHT_MPS) * closing_rate_mps
        return np.array([rssi_dbfs, cfo_hz], dtype=float)

    def _measurement_jacobian(self) -> np.ndarray:
        range_m = max(self.state[0], self.config.minimum_range_m)
        return np.array(
            [
                [-(10.0 * self.config.path_loss_exponent) / (math.log(10.0) * range_m), 0.0, 1.0],
                [0.0, -(self.config.carrier_frequency_hz / SPEED_OF_LIGHT_MPS), 0.0],
            ],
            dtype=float,
        )

    def update(self, observation: RadioObservation) -> None:
        measurement = np.array([observation.rssi_dbfs, observation.cfo_hz], dtype=float)
        predicted = self._measurement_model()
        jacobian = self._measurement_jacobian()

        confidence_scale = 1.0 / max(observation.confidence, 0.15)
        measurement_noise = np.diag(self.config.measurement_noise_diag) * confidence_scale

        innovation = measurement - predicted
        innovation_covariance = jacobian @ self.covariance @ jacobian.T + measurement_noise
        kalman_gain = self.covariance @ jacobian.T @ np.linalg.inv(innovation_covariance)

        identity = np.eye(3)
        self.state = self.state + kalman_gain @ innovation
        self.state[0] = max(self.state[0], self.config.minimum_range_m)
        joseph_factor = identity - kalman_gain @ jacobian
        self.covariance = (
            joseph_factor @ self.covariance @ joseph_factor.T + kalman_gain @ measurement_noise @ kalman_gain.T
        )

    def _confidence(self, observation_confidence: float, telemetry: TelemetrySample | None) -> float:
        range_sigma_m = math.sqrt(max(self.covariance[0, 0], 0.0))
        uncertainty_penalty = min(0.7, range_sigma_m / max(self.state[0] * 2.0, 1.0))
        motion_bonus = 0.1 if telemetry and telemetry.ground_speed_mps >= 1.0 else 0.0
        return _clamp(observation_confidence + motion_bonus - uncertainty_penalty, 0.0, 1.0)

    def snapshot(self, timestamp_s: float, observation_confidence: float, telemetry: TelemetrySample | None) -> ThreatEstimate:
        range_m = max(float(self.state[0]), self.config.minimum_range_m)
        closing_rate_mps = float(self.state[1])
        effective_power_db = float(self.state[2])
        time_to_impact_s = None
        if closing_rate_mps < -0.1:
            time_to_impact_s = range_m / abs(closing_rate_mps)

        return ThreatEstimate(
            timestamp_s=timestamp_s,
            range_m=range_m,
            closing_rate_mps=closing_rate_mps,
            effective_power_db=effective_power_db,
            time_to_impact_s=time_to_impact_s,
            covariance_diag=(
                float(self.covariance[0, 0]),
                float(self.covariance[1, 1]),
                float(self.covariance[2, 2]),
            ),
            confidence=self._confidence(observation_confidence, telemetry),
        )

    def step(
        self,
        observation: RadioObservation,
        telemetry: TelemetrySample | None = None,
    ) -> ThreatEstimate:
        if self.last_timestamp_s is not None:
            dt_s = max(observation.timestamp_s - self.last_timestamp_s, 1e-3)
            self.predict(dt_s)

        self.update(observation)
        self.last_timestamp_s = observation.timestamp_s
        return self.snapshot(observation.timestamp_s, observation.confidence, telemetry)

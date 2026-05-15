from __future__ import annotations

import math

import numpy as np

from kinetic_ranger.config import EstimatorConfig
from kinetic_ranger.models import RadioObservation, TelemetrySample, ThreatEstimate

SPEED_OF_LIGHT_MPS = 299_792_458.0


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


class ClosingThreatEKF:
    # Kalman filter over (rssi_dbfs, rssi_slope_db_per_s, closing_rate_mps) (does not assume Tx power anymore)

    def __init__(self, config: EstimatorConfig) -> None:
        self.config = config
        self.state = np.array(
            [
                config.initial_rssi_dbfs,
                config.initial_rssi_slope_db_per_s,
                config.initial_closing_rate_mps,
            ],
            dtype=float,
        )
        self.covariance = np.diag(config.initial_covariance_diag)
        self.last_timestamp_s: float | None = None

        fc = config.carrier_frequency_hz
        self._doppler_gain = -fc / SPEED_OF_LIGHT_MPS

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
        self.covariance = transition @ self.covariance @ transition.T + process_noise

    def _measurement_jacobian(self) -> np.ndarray:
        # Linear in the state: H is constant.
        return np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 0.0, self._doppler_gain],
            ],
            dtype=float,
        )

    def update(self, observation: RadioObservation) -> None:
        measurement = np.array([observation.rssi_dbfs, observation.cfo_hz], dtype=float)
        jacobian = self._measurement_jacobian()
        predicted = jacobian @ self.state

        confidence_scale = 1.0 / max(observation.confidence, 0.15)
        measurement_noise = np.diag(self.config.measurement_noise_diag) * confidence_scale

        innovation = measurement - predicted
        innovation_covariance = jacobian @ self.covariance @ jacobian.T + measurement_noise
        kalman_gain = self.covariance @ jacobian.T @ np.linalg.inv(innovation_covariance)

        identity = np.eye(3)
        self.state = self.state + kalman_gain @ innovation
        joseph_factor = identity - kalman_gain @ jacobian
        self.covariance = (
            joseph_factor @ self.covariance @ joseph_factor.T
            + kalman_gain @ measurement_noise @ kalman_gain.T
        )

    def _time_to_impact(self, rssi_slope_db_per_s: float, closing_rate_mps: float) -> float | None:
        # Doppler must agree we're closing.
        if closing_rate_mps >= -0.1:
            return None
        # RSSI must be rising fast enough for a stable slope-based TTI.
        if rssi_slope_db_per_s <= self.config.tti_slope_floor_db_per_s:
            return None
        n = self.config.path_loss_exponent
        return (10.0 * n) / (math.log(10.0) * rssi_slope_db_per_s)

    def _confidence(
        self,
        observation_confidence: float,
        telemetry: TelemetrySample | None,
        rssi_slope_db_per_s: float,
        closing_rate_mps: float,
    ) -> float:
        slope_sigma = math.sqrt(max(self.covariance[1, 1], 0.0))
        slope_magnitude = max(abs(rssi_slope_db_per_s), 1e-3)
        slope_penalty = min(0.5, slope_sigma / (slope_magnitude + slope_sigma + 1e-6))

        # Reward Doppler/slope sign agreement: closing (negative rate) + rising RSSI.
        if closing_rate_mps < -0.1 and rssi_slope_db_per_s > 0.0:
            agreement_bonus = 0.15
        elif closing_rate_mps > 0.1 and rssi_slope_db_per_s < 0.0:
            agreement_bonus = 0.05  # consistent retreat — still consistent, lower threat
        else:
            agreement_bonus = -0.1

        motion_bonus = 0.05 if telemetry and telemetry.ground_speed_mps >= 1.0 else 0.0
        return _clamp(
            observation_confidence + agreement_bonus + motion_bonus - slope_penalty,
            0.0,
            1.0,
        )

    def snapshot(
        self,
        timestamp_s: float,
        observation_confidence: float,
        telemetry: TelemetrySample | None,
    ) -> ThreatEstimate:
        rssi_dbfs = float(self.state[0])
        rssi_slope_db_per_s = float(self.state[1])
        closing_rate_mps = float(self.state[2])
        time_to_impact_s = self._time_to_impact(rssi_slope_db_per_s, closing_rate_mps)

        return ThreatEstimate(
            timestamp_s=timestamp_s,
            rssi_dbfs=rssi_dbfs,
            rssi_slope_db_per_s=rssi_slope_db_per_s,
            closing_rate_mps=closing_rate_mps,
            time_to_impact_s=time_to_impact_s,
            covariance_diag=(
                float(self.covariance[0, 0]),
                float(self.covariance[1, 1]),
                float(self.covariance[2, 2]),
            ),
            confidence=self._confidence(
                observation_confidence, telemetry, rssi_slope_db_per_s, closing_rate_mps
            ),
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

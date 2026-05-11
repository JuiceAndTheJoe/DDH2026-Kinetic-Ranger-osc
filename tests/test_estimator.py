from __future__ import annotations

import numpy as np

from kinetic_ranger.config import EstimatorConfig, RadioConfig, SimulationConfig
from kinetic_ranger.estimation.ekf import ClosingThreatEKF
from kinetic_ranger.radio.capture import SimulatedApproachCapture
from kinetic_ranger.radio.features import extract_observation


def test_estimator_tracks_closing_target() -> None:
    np.random.seed(7)

    radio = RadioConfig(
        sample_rate_hz=200_000.0,
        center_frequency_hz=2_437_000_000.0,
        buffer_size=4096,
    )
    simulation = SimulationConfig(
        steps=24,
        dt_s=0.5,
        start_range_m=220.0,
        end_range_m=20.0,
        effective_power_db=-6.0,
        path_loss_exponent=2.15,
        noise_std=0.0005,
    )
    estimator_config = EstimatorConfig(
        carrier_frequency_hz=radio.center_frequency_hz,
        path_loss_exponent=simulation.path_loss_exponent,
        initial_range_m=250.0,
        initial_closing_rate_mps=-2.0,
        initial_effective_power_db=simulation.effective_power_db,
    )

    capture = SimulatedApproachCapture(radio, simulation)
    estimator = ClosingThreatEKF(estimator_config)

    estimates = []
    for window in capture.iter_windows():
        observation = extract_observation(window)
        estimates.append(estimator.step(observation))

    assert estimates[-1].range_m < estimates[0].range_m
    assert estimates[-1].closing_rate_mps < -1.0
    assert estimates[-1].time_to_impact_s is not None
    assert estimates[-1].confidence > 0.3

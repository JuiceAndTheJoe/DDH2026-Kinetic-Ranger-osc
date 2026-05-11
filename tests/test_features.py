from __future__ import annotations

import numpy as np
import pytest

from kinetic_ranger.models import IQWindow
from kinetic_ranger.radio.features import extract_observation, estimate_cfo_hz, power_dbfs


def test_power_dbfs_matches_complex_tone_amplitude() -> None:
    amplitude = 0.5
    sample_rate_hz = 200_000.0
    sample_count = 4096
    tone_hz = 12_500.0
    sample_times = np.arange(sample_count) / sample_rate_hz
    samples = amplitude * np.exp(1j * 2.0 * np.pi * tone_hz * sample_times)

    measured_dbfs = power_dbfs(samples)
    assert measured_dbfs == pytest.approx(20.0 * np.log10(amplitude), abs=0.25)


def test_estimate_cfo_hz_recovers_known_tone() -> None:
    sample_rate_hz = 200_000.0
    sample_count = 4096
    tone_hz = 8_000.0
    sample_times = np.arange(sample_count) / sample_rate_hz
    samples = np.exp(1j * 2.0 * np.pi * tone_hz * sample_times)

    measured_hz = estimate_cfo_hz(samples, sample_rate_hz)
    assert measured_hz == pytest.approx(tone_hz, abs=5.0)


def test_extract_observation_returns_confident_tone_metrics() -> None:
    sample_rate_hz = 250_000.0
    sample_count = 4096
    tone_hz = 10_000.0
    sample_times = np.arange(sample_count) / sample_rate_hz
    samples = 0.35 * np.exp(1j * 2.0 * np.pi * tone_hz * sample_times)

    window = IQWindow(
        samples=samples.astype(np.complex128),
        sample_rate_hz=sample_rate_hz,
        center_frequency_hz=2_437_000_000.0,
        timestamp_s=1.0,
    )
    observation = extract_observation(window)

    assert observation.cfo_hz == pytest.approx(tone_hz, abs=5.0)
    assert observation.snr_db > 10.0
    assert observation.confidence > 0.5

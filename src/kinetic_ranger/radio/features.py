from __future__ import annotations

import math

import numpy as np

from kinetic_ranger.models import IQWindow, RadioObservation

EPSILON = 1e-12


def power_dbfs(samples: np.ndarray) -> float:
    return float(10.0 * np.log10(np.mean(np.abs(samples) ** 2) + EPSILON))


def estimate_cfo_hz(samples: np.ndarray, sample_rate_hz: float) -> float:
    if len(samples) < 2:
        return 0.0

    phase_step = np.angle(np.mean(np.conjugate(samples[:-1]) * samples[1:]))
    return float(phase_step * sample_rate_hz / (2.0 * np.pi))


def _spectral_metrics(samples: np.ndarray, sample_rate_hz: float) -> tuple[float, float, float]:
    windowed = samples * np.hanning(len(samples))
    spectrum = np.fft.fftshift(np.fft.fft(windowed))
    power_linear = np.abs(spectrum) ** 2
    power_db = 10.0 * np.log10(power_linear + EPSILON)
    freqs = np.fft.fftshift(np.fft.fftfreq(len(samples), d=1.0 / sample_rate_hz))

    peak_db = float(np.max(power_db))
    noise_floor_db = float(np.percentile(power_db, 25))
    snr_db = peak_db - noise_floor_db

    occupied = np.where(power_db >= (peak_db - 6.0))[0]
    if len(occupied) >= 2:
        spectral_width_hz = float(freqs[occupied[-1]] - freqs[occupied[0]])
    else:
        spectral_width_hz = 0.0

    return noise_floor_db, snr_db, spectral_width_hz


def score_confidence(snr_db: float, sample_count: int) -> float:
    snr_component = 1.0 / (1.0 + math.exp(-(snr_db - 6.0) / 3.0))
    sample_component = min(1.0, math.log10(max(sample_count, 10)) / 4.0)
    confidence = 0.05 + 0.95 * snr_component * sample_component
    return float(max(0.0, min(1.0, confidence)))


def extract_observation(window: IQWindow, agc_enabled: bool = False) -> RadioObservation:
    rssi_dbfs = power_dbfs(window.samples)
    cfo_hz = estimate_cfo_hz(window.samples, window.sample_rate_hz)
    noise_floor_dbfs, snr_db, spectral_width_hz = _spectral_metrics(
        window.samples,
        window.sample_rate_hz,
    )
    confidence = score_confidence(snr_db, len(window.samples))

    return RadioObservation(
        timestamp_s=window.timestamp_s,
        center_frequency_hz=window.center_frequency_hz,
        rssi_dbfs=rssi_dbfs,
        cfo_hz=cfo_hz,
        snr_db=snr_db,
        confidence=confidence,
        noise_floor_dbfs=noise_floor_dbfs,
        agc_enabled=agc_enabled,
        spectral_width_hz=spectral_width_hz,
    )

from __future__ import annotations

import math
import time
from typing import Any

import numpy as np

from kinetic_ranger.config import RadioConfig, SimulationConfig
from kinetic_ranger.models import IQWindow

SPEED_OF_LIGHT_MPS = 299_792_458.0


def _db_to_linear_amplitude(value_db: float) -> float:
    return 10 ** (value_db / 20.0)


class SimulatedApproachCapture:
    """Generate synthetic IQ windows for a closing transmitter."""

    def __init__(self, radio_config: RadioConfig, simulation_config: SimulationConfig) -> None:
        self.radio_config = radio_config
        self.simulation_config = simulation_config
        self._ranges = np.linspace(
            simulation_config.start_range_m,
            simulation_config.end_range_m,
            simulation_config.steps,
        )

    def iter_windows(self) -> list[IQWindow]:
        windows: list[IQWindow] = []
        sample_times = np.arange(self.radio_config.buffer_size) / self.radio_config.sample_rate_hz

        for index, range_m in enumerate(self._ranges):
            if index == 0:
                radial_velocity_mps = (self._ranges[1] - self._ranges[0]) / self.simulation_config.dt_s
            elif index == len(self._ranges) - 1:
                radial_velocity_mps = (self._ranges[-1] - self._ranges[-2]) / self.simulation_config.dt_s
            else:
                radial_velocity_mps = (
                    self._ranges[index + 1] - self._ranges[index - 1]
                ) / (2.0 * self.simulation_config.dt_s)

            cfo_hz = -(self.radio_config.center_frequency_hz / SPEED_OF_LIGHT_MPS) * radial_velocity_mps
            rssi_dbfs = self.simulation_config.effective_power_db - (
                10.0 * self.simulation_config.path_loss_exponent * math.log10(max(range_m, 1.0))
            )
            amplitude = _db_to_linear_amplitude(rssi_dbfs)
            phase = 2.0 * np.pi * cfo_hz * sample_times
            tone = amplitude * np.exp(1j * phase)
            noise = self.simulation_config.noise_std * (
                np.random.normal(size=self.radio_config.buffer_size)
                + 1j * np.random.normal(size=self.radio_config.buffer_size)
            )
            windows.append(
                IQWindow(
                    samples=(tone + noise).astype(np.complex128),
                    sample_rate_hz=self.radio_config.sample_rate_hz,
                    center_frequency_hz=self.radio_config.center_frequency_hz,
                    timestamp_s=index * self.simulation_config.dt_s,
                )
            )

        return windows


class AntSdrIioCapture:
    """Best-effort live capture path for Pluto-compatible IIO firmware."""

    def __init__(self, radio_config: RadioConfig) -> None:
        try:
            import adi  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional hardware package
            raise RuntimeError(
                "pyadi-iio is required for live IIO capture. Install the 'hardware' extra first."
            ) from exc

        self.radio_config = radio_config
        pluto_constructor: Any = getattr(adi, "Pluto")
        self._device: Any = pluto_constructor(uri=radio_config.uri)
        self._device.sample_rate = int(radio_config.sample_rate_hz)
        self._device.rx_lo = int(radio_config.center_frequency_hz)
        self._device.rx_buffer_size = int(radio_config.buffer_size)

        if radio_config.gain_mode == "manual":
            self._device.gain_control_mode_chan0 = "manual"
            self._device.rx_hardwaregain_chan0 = float(radio_config.gain_db)
        else:
            self._device.gain_control_mode_chan0 = "slow_attack"

    def read_window(self) -> IQWindow:
        raw = self._device.rx()
        if isinstance(raw, (list, tuple)):
            samples = np.asarray(raw[0], dtype=np.complex128)
        else:
            samples = np.asarray(raw, dtype=np.complex128)

        return IQWindow(
            samples=samples.flatten(),
            sample_rate_hz=self.radio_config.sample_rate_hz,
            center_frequency_hz=self.radio_config.center_frequency_hz,
            timestamp_s=time.time(),
        )

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any
import tomllib


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "default.toml"


def _coerce_tuple3(values: tuple[float, ...]) -> tuple[float, float, float]:
    if len(values) != 3:
        raise ValueError(f"expected exactly 3 values, got {len(values)}")
    return (float(values[0]), float(values[1]), float(values[2]))


def _coerce_tuple2(values: tuple[float, ...]) -> tuple[float, float]:
    if len(values) != 2:
        raise ValueError(f"expected exactly 2 values, got {len(values)}")
    return (float(values[0]), float(values[1]))


@dataclass(slots=True)
class RadioConfig:
    uri: str = "ip:192.168.1.10"
    sample_rate_hz: float = 1_000_000.0
    center_frequency_hz: float = 2_437_000_000.0
    buffer_size: int = 8192
    gain_db: float = 30.0
    gain_mode: str = "manual"


@dataclass(slots=True)
class TelemetryConfig:
    csv_path: str = ""
    time_offset_s: float = 0.0
    use_ground_speed: bool = True


@dataclass(slots=True)
class EstimatorConfig:
    carrier_frequency_hz: float = 2_437_000_000.0
    path_loss_exponent: float = 2.15
    initial_range_m: float = 180.0
    initial_closing_rate_mps: float = -3.0
    initial_effective_power_db: float = -6.0
    initial_covariance_diag: tuple[float, float, float] = (625.0, 16.0, 36.0)
    process_noise_diag: tuple[float, float, float] = (36.0, 4.0, 1.0)
    measurement_noise_diag: tuple[float, float] = (9.0, 25.0)
    minimum_range_m: float = 1.0

    def __post_init__(self) -> None:
        self.initial_covariance_diag = _coerce_tuple3(self.initial_covariance_diag)
        self.process_noise_diag = _coerce_tuple3(self.process_noise_diag)
        self.measurement_noise_diag = _coerce_tuple2(self.measurement_noise_diag)


@dataclass(slots=True)
class AlertConfig:
    tti_threshold_s: float = 12.0
    min_closing_rate_mps: float = 2.0
    min_confidence: float = 0.55
    consecutive_hits: int = 3
    cooldown_s: float = 5.0
    clear_factor: float = 1.35


@dataclass(slots=True)
class SimulationConfig:
    steps: int = 30
    dt_s: float = 0.5
    start_range_m: float = 220.0
    end_range_m: float = 25.0
    effective_power_db: float = -6.0
    path_loss_exponent: float = 2.15
    noise_std: float = 0.0005


@dataclass(slots=True)
class AppConfig:
    radio: RadioConfig = field(default_factory=RadioConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    estimator: EstimatorConfig = field(default_factory=EstimatorConfig)
    alert: AlertConfig = field(default_factory=AlertConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)


def _dataclass_from_mapping(cls: type[Any], data: dict[str, Any] | None) -> Any:
    if not data:
        return cls()

    valid_keys = {item.name for item in fields(cls)}
    kwargs = {key: value for key, value in data.items() if key in valid_keys}
    return cls(**kwargs)


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))

    return AppConfig(
        radio=_dataclass_from_mapping(RadioConfig, raw.get("radio")),
        telemetry=_dataclass_from_mapping(TelemetryConfig, raw.get("telemetry")),
        estimator=_dataclass_from_mapping(EstimatorConfig, raw.get("estimator")),
        alert=_dataclass_from_mapping(AlertConfig, raw.get("alert")),
        simulation=_dataclass_from_mapping(SimulationConfig, raw.get("simulation")),
    )

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from kinetic_ranger.alerting.rules import AlertRuleEngine
from kinetic_ranger.config import (
    AlertConfig,
    AppConfig,
    EstimatorConfig,
    RadioConfig,
    SimulationConfig,
    TelemetryConfig,
)
from kinetic_ranger.estimation.ekf import ClosingThreatEKF
from kinetic_ranger.logging import RunReader, RunWriter, export_run
from kinetic_ranger.radio.capture import SimulatedApproachCapture
from kinetic_ranger.radio.features import extract_observation


def _fixture_config() -> AppConfig:
    radio = RadioConfig(sample_rate_hz=200_000.0, buffer_size=2048)
    simulation = SimulationConfig(
        steps=10,
        dt_s=0.5,
        start_range_m=200.0,
        end_range_m=30.0,
        effective_power_db=-6.0,
        path_loss_exponent=2.15,
        noise_std=0.0005,
    )
    estimator = EstimatorConfig(
        carrier_frequency_hz=radio.center_frequency_hz,
        path_loss_exponent=simulation.path_loss_exponent,
        initial_range_m=220.0,
        initial_closing_rate_mps=-2.0,
        initial_effective_power_db=simulation.effective_power_db,
    )
    return AppConfig(
        radio=radio,
        telemetry=TelemetryConfig(),
        estimator=estimator,
        alert=AlertConfig(),
        simulation=simulation,
    )


def test_record_export_replay_roundtrip(tmp_path: Path) -> None:
    """Record a run, export CSVs, replay it, and confirm estimates match."""
    np.random.seed(7)
    config = _fixture_config()

    capture = SimulatedApproachCapture(config.radio, config.simulation)
    ekf = ClosingThreatEKF(config.estimator)
    alerts = AlertRuleEngine(config.alert)

    original_estimates = []
    with RunWriter(tmp_path, "simulate", config) as writer:
        for window in capture.iter_windows():
            observation = extract_observation(window, agc_enabled=False)
            estimate = ekf.step(observation)
            alert = alerts.evaluate(estimate, observation)
            writer.log_snapshot(observation, estimate, alert, None)
            original_estimates.append(estimate)
        run_path = writer.path

    # Run artifact landed on disk.
    assert (run_path / "manifest.json").exists()
    assert (run_path / "snapshots.jsonl").exists()
    manifest = json.loads((run_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["mode"] == "simulate"
    assert manifest["tick_count"] == config.simulation.steps

    # Export produces CSVs with the right schema and row count.
    written = export_run(run_path)
    assert written["observations"] == run_path / "observations.csv"
    assert written["alerts"] == run_path / "alerts.csv"
    # No telemetry was logged in this fixture, so telemetry.csv must not be retained.
    assert "telemetry" not in written
    assert not (run_path / "telemetry.csv").exists()

    obs_lines = (run_path / "observations.csv").read_text(encoding="utf-8").splitlines()
    assert obs_lines[0].startswith("timestamp_s,center_frequency_hz,rssi_dbfs,")
    assert len(obs_lines) == config.simulation.steps + 1  # header + N rows

    # Replay with a fresh estimator and confirm the trajectory is reproduced.
    reader = RunReader(run_path)
    replay_ekf = ClosingThreatEKF(config.estimator)
    replay_estimates = [
        replay_ekf.step(observation, telemetry)
        for observation, telemetry in reader.iter_observations()
    ]

    assert len(replay_estimates) == len(original_estimates)
    for original, replayed in zip(original_estimates, replay_estimates):
        assert replayed.timestamp_s == pytest.approx(original.timestamp_s, abs=1e-9)
        assert replayed.range_m == pytest.approx(original.range_m, abs=1e-9)
        assert replayed.closing_rate_mps == pytest.approx(
            original.closing_rate_mps, abs=1e-9
        )
        assert replayed.effective_power_db == pytest.approx(
            original.effective_power_db, abs=1e-9
        )


def test_run_reader_rejects_missing_manifest(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        RunReader(tmp_path)

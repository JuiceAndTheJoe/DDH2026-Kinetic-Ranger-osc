from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable

from kinetic_ranger.alerting.rules import AlertRuleEngine
from kinetic_ranger.config import AppConfig, load_config
from kinetic_ranger.estimation.ekf import ClosingThreatEKF
from kinetic_ranger.logging.session_logger import SessionLogger
from kinetic_ranger.models import RadioObservation
from kinetic_ranger.radio.capture import AntSdrIioCapture, SimulatedApproachCapture
from kinetic_ranger.radio.features import extract_observation
from kinetic_ranger.telemetry.ingest import TelemetryTrack, load_telemetry_csv
from kinetic_ranger.ui.dashboard import format_console_snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kinetic Ranger utilities")
    parser.add_argument("--config", default=None, help="Path to TOML config file")

    subparsers = parser.add_subparsers(dest="command", required=True)

    simulate = subparsers.add_parser("simulate", help="Run the synthetic approach simulation")
    simulate.add_argument("--log-dir", default=None, help="Optional output directory for JSONL logs")

    replay = subparsers.add_parser("replay", help="Replay observations from a CSV file")
    replay.add_argument("observations", help="CSV file with extracted observations")
    replay.add_argument("--telemetry", default=None, help="Optional telemetry CSV")
    replay.add_argument("--log-dir", default=None, help="Optional output directory for JSONL logs")

    live = subparsers.add_parser("live", help="Read from an IIO-compatible device")
    live.add_argument("--iterations", type=int, default=10, help="How many windows to read before stopping")
    live.add_argument("--log-dir", default=None, help="Optional output directory for JSONL logs")

    return parser


def _load_observation_rows(path: str | Path) -> list[RadioObservation]:
    observations: list[RadioObservation] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            observations.append(
                RadioObservation(
                    timestamp_s=float(row["timestamp_s"]),
                    center_frequency_hz=float(row["center_frequency_hz"]),
                    rssi_dbfs=float(row["rssi_dbfs"]),
                    cfo_hz=float(row["cfo_hz"]),
                    snr_db=float(row["snr_db"]),
                    confidence=float(row["confidence"]),
                    noise_floor_dbfs=float(row.get("noise_floor_dbfs") or 0.0),
                    agc_enabled=str(row.get("agc_enabled", "false")).lower() == "true",
                    spectral_width_hz=float(row.get("spectral_width_hz") or 0.0),
                )
            )
    return observations


def _run_pipeline(
    observations: Iterable[RadioObservation],
    config: AppConfig,
    telemetry_track: TelemetryTrack | None = None,
    log_dir: str | None = None,
) -> int:
    estimator = ClosingThreatEKF(config.estimator)
    alert_engine = AlertRuleEngine(config.alert)
    logger = SessionLogger(log_dir) if log_dir else None

    try:
        for observation in observations:
            telemetry = telemetry_track.at(observation.timestamp_s) if telemetry_track else None
            estimate = estimator.step(observation, telemetry)
            alert = alert_engine.evaluate(estimate, observation)
            print(format_console_snapshot(observation, estimate, alert))
            if logger:
                logger.log_snapshot(observation, estimate, alert, telemetry)
    finally:
        if logger:
            logger.close()

    return 0


def handle_simulate(config: AppConfig, log_dir: str | None) -> int:
    capture = SimulatedApproachCapture(config.radio, config.simulation)
    observations = [extract_observation(window, agc_enabled=False) for window in capture.iter_windows()]
    return _run_pipeline(observations, config, log_dir=log_dir)


def handle_replay(config: AppConfig, observation_path: str, telemetry_path: str | None, log_dir: str | None) -> int:
    observations = _load_observation_rows(observation_path)
    telemetry_track = TelemetryTrack(load_telemetry_csv(telemetry_path)) if telemetry_path else None
    return _run_pipeline(observations, config, telemetry_track=telemetry_track, log_dir=log_dir)


def handle_live(config: AppConfig, iterations: int, log_dir: str | None) -> int:
    capture = AntSdrIioCapture(config.radio)
    observations = []
    for _ in range(iterations):
        window = capture.read_window()
        observations.append(extract_observation(window, agc_enabled=config.radio.gain_mode != "manual"))
    return _run_pipeline(observations, config, log_dir=log_dir)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)

    if args.command == "simulate":
        return handle_simulate(config, args.log_dir)
    if args.command == "replay":
        return handle_replay(config, args.observations, args.telemetry, args.log_dir)
    if args.command == "live":
        return handle_live(config, args.iterations, args.log_dir)

    parser.error(f"unsupported command: {args.command}")
    return 2

"""Flat-CSV export from a recorded run directory."""
from __future__ import annotations

import csv
from pathlib import Path

from kinetic_ranger.logging.run_reader import RunReader

OBSERVATION_FIELDS = [
    "timestamp_s",
    "center_frequency_hz",
    "rssi_dbfs",
    "cfo_hz",
    "snr_db",
    "confidence",
    "noise_floor_dbfs",
    "agc_enabled",
    "spectral_width_hz",
]
TELEMETRY_FIELDS = [
    "timestamp_s",
    "latitude_deg",
    "longitude_deg",
    "altitude_m",
    "ground_speed_mps",
    "heading_deg",
    "local_east_m",
    "local_north_m",
]
ALERT_FIELDS = [
    "timestamp_s",
    "active",
    "severity",
    "reason",
    "sustained_hits",
    "cooldown_remaining_s",
]


def export_run(run_dir: str | Path) -> dict[str, Path]:
    """Read snapshots.jsonl and write observations.csv, alerts.csv, telemetry.csv.

    telemetry.csv is only retained when at least one telemetry sample was logged.
    """
    reader = RunReader(run_dir)
    run_path = reader.path

    obs_path = run_path / "observations.csv"
    alerts_path = run_path / "alerts.csv"
    telemetry_path = run_path / "telemetry.csv"

    obs_handle = obs_path.open("w", encoding="utf-8", newline="")
    alerts_handle = alerts_path.open("w", encoding="utf-8", newline="")
    telemetry_handle = telemetry_path.open("w", encoding="utf-8", newline="")

    wrote_telemetry = False
    try:
        obs_writer = csv.DictWriter(obs_handle, fieldnames=OBSERVATION_FIELDS)
        alerts_writer = csv.DictWriter(alerts_handle, fieldnames=ALERT_FIELDS)
        telemetry_writer = csv.DictWriter(telemetry_handle, fieldnames=TELEMETRY_FIELDS)

        obs_writer.writeheader()
        alerts_writer.writeheader()
        telemetry_writer.writeheader()

        for observation, _estimate, alert, telemetry in reader.iter_snapshots():
            obs_writer.writerow(observation.to_dict())
            alerts_writer.writerow(alert.to_dict())
            if telemetry is not None:
                telemetry_writer.writerow(telemetry.to_dict())
                wrote_telemetry = True
    finally:
        obs_handle.close()
        alerts_handle.close()
        telemetry_handle.close()

    written: dict[str, Path] = {"observations": obs_path, "alerts": alerts_path}
    if wrote_telemetry:
        written["telemetry"] = telemetry_path
    else:
        telemetry_path.unlink(missing_ok=True)
    return written

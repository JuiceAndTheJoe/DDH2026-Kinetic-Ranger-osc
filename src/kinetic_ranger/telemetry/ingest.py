from __future__ import annotations

import csv
from bisect import bisect_left
from pathlib import Path

from kinetic_ranger.models import TelemetrySample

EARTH_RADIUS_M = 6_378_137.0


TIMESTAMP_KEYS = ("timestamp_s", "timestamp", "time_s", "time")
LAT_KEYS = ("latitude_deg", "lat", "latitude")
LON_KEYS = ("longitude_deg", "lon", "longitude")
ALT_KEYS = ("altitude_m", "alt_m", "altitude")
SPEED_KEYS = ("ground_speed_mps", "speed_mps", "groundspeed", "speed")
HEADING_KEYS = ("heading_deg", "heading", "yaw_deg")


def _get_value(row: dict[str, str], keys: tuple[str, ...], default: float = 0.0) -> float:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return float(value)
    return default


def _local_offset_m(
    latitude_deg: float,
    longitude_deg: float,
    reference_latitude_deg: float,
    reference_longitude_deg: float,
) -> tuple[float, float]:
    delta_lat_rad = (latitude_deg - reference_latitude_deg) * 3.141592653589793 / 180.0
    delta_lon_rad = (longitude_deg - reference_longitude_deg) * 3.141592653589793 / 180.0
    mean_lat_rad = (latitude_deg + reference_latitude_deg) * 0.5 * 3.141592653589793 / 180.0

    north_m = delta_lat_rad * EARTH_RADIUS_M
    east_m = delta_lon_rad * EARTH_RADIUS_M * __import__("math").cos(mean_lat_rad)
    return east_m, north_m


def load_telemetry_csv(path: str | Path | None) -> list[TelemetrySample]:
    if not path:
        return []

    samples: list[TelemetrySample] = []
    reference_latitude_deg: float | None = None
    reference_longitude_deg: float | None = None

    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            latitude_deg = _get_value(row, LAT_KEYS)
            longitude_deg = _get_value(row, LON_KEYS)
            if reference_latitude_deg is None or reference_longitude_deg is None:
                reference_latitude_deg = latitude_deg
                reference_longitude_deg = longitude_deg

            east_m, north_m = _local_offset_m(
                latitude_deg,
                longitude_deg,
                reference_latitude_deg,
                reference_longitude_deg,
            )

            samples.append(
                TelemetrySample(
                    timestamp_s=_get_value(row, TIMESTAMP_KEYS),
                    latitude_deg=latitude_deg,
                    longitude_deg=longitude_deg,
                    altitude_m=_get_value(row, ALT_KEYS),
                    ground_speed_mps=_get_value(row, SPEED_KEYS),
                    heading_deg=_get_value(row, HEADING_KEYS),
                    local_east_m=east_m,
                    local_north_m=north_m,
                )
            )

    return samples


class TelemetryTrack:
    def __init__(self, samples: list[TelemetrySample]) -> None:
        self.samples = sorted(samples, key=lambda sample: sample.timestamp_s)
        self._timestamps = [sample.timestamp_s for sample in self.samples]

    def at(self, timestamp_s: float) -> TelemetrySample | None:
        if not self.samples:
            return None

        index = bisect_left(self._timestamps, timestamp_s)
        if index <= 0:
            return self.samples[0]
        if index >= len(self.samples):
            return self.samples[-1]

        left = self.samples[index - 1]
        right = self.samples[index]
        if abs(left.timestamp_s - timestamp_s) <= abs(right.timestamp_s - timestamp_s):
            return left
        return right

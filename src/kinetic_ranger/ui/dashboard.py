from __future__ import annotations

from kinetic_ranger.models import AlertDecision, RadioObservation, ThreatEstimate


def _format_tti(value: float | None) -> str:
    return f"{value:6.2f}s" if value is not None else "   n/a"


def format_console_snapshot(
    observation: RadioObservation,
    estimate: ThreatEstimate,
    alert: AlertDecision,
) -> str:
    state = "ALERT" if alert.active else "TRACK"
    return (
        f"[{observation.timestamp_s:6.2f}s] {state:<5} "
        f"RSSI={observation.rssi_dbfs:7.2f} dBFS "
        f"CFO={observation.cfo_hz:9.2f} Hz "
        f"Range={estimate.range_m:7.2f} m "
        f"CloseRate={estimate.closing_rate_mps:7.2f} m/s "
        f"TTI={_format_tti(estimate.time_to_impact_s)} "
        f"Conf={estimate.confidence:0.2f} "
        f"Reason={alert.reason}"
    )

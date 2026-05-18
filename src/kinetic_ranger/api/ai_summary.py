"""REST route for AI-generated summaries of replayed drone movement events."""
from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter, Request, HTTPException

from kinetic_ranger.logging import RunReader
from kinetic_ranger.models import AlertDecision, RadioObservation, TelemetrySample, ThreatEstimate
from kinetic_ranger.ai.vertex_summarizer import (
    AISummaryError,
    VertexAISummarizer,
    ai_summaries_enabled,
)

router = APIRouter()

_SEVERITY_RANK = {"info": 1, "warning": 2, "critical": 3}
_SEVERITY_TO_THREAT = {"info": "LOW", "warning": "HIGH", "critical": "CRITICAL"}


def _snapshot_fact(
    frame_index: int,
    observation: RadioObservation,
    estimate: ThreatEstimate,
    alert: AlertDecision,
) -> dict:
    return {
        "frame_index": frame_index,
        "time_s": round(observation.timestamp_s, 2),
        "rssi_db": round(observation.rssi_dbfs, 2),
        "severity": str(alert.severity).lower(),
        "threat_level": _SEVERITY_TO_THREAT.get(str(alert.severity).lower(), "LOW"),
        "alert_active": bool(alert.active),
        "reason": alert.reason,
        "ttc_s": round(estimate.time_to_impact_s, 2) if estimate.time_to_impact_s is not None else None,
        "closing_rate_mps": round(estimate.closing_rate_mps, 2),
        "confidence": round(min(estimate.confidence, observation.confidence), 3),
    }


def _signal_trend(start_rssi_db: float, end_rssi_db: float) -> str:
    delta = end_rssi_db - start_rssi_db
    if delta >= 1.5:
        return "strengthening"
    if delta <= -1.5:
        return "weakening"
    return "stable"


def _unique_highlights(candidates: list[dict]) -> list[dict]:
    seen: set[int] = set()
    result: list[dict] = []
    for item in candidates:
        frame_index = item["frame_index"]
        if frame_index in seen:
            continue
        seen.add(frame_index)
        result.append(item)
    return result


def _build_run_facts(
    run_id: str,
    snapshots: Iterable[
        tuple[RadioObservation, ThreatEstimate, AlertDecision, TelemetrySample | None, float | None]
    ],
) -> dict:
    total_frames = 0
    active_alert_frames = 0
    first_fact: dict | None = None
    last_fact: dict | None = None
    first_active_fact: dict | None = None
    peak_fact: dict | None = None
    min_ttc_fact: dict | None = None
    min_active_ttc_s: float | None = None
    peak_rssi_db: float | None = None
    reasons: set[str] = set()

    for frame_index, (observation, estimate, alert, telemetry, _range_m) in enumerate(snapshots):
        del telemetry
        fact = _snapshot_fact(frame_index, observation, estimate, alert)
        total_frames += 1
        reasons.add(alert.reason)
        if first_fact is None:
            first_fact = fact
        last_fact = fact
        peak_rssi_db = fact["rssi_db"] if peak_rssi_db is None else max(peak_rssi_db, fact["rssi_db"])
        if fact["alert_active"]:
            active_alert_frames += 1
            if first_active_fact is None:
                first_active_fact = fact
            if fact["ttc_s"] is not None and (
                min_active_ttc_s is None or fact["ttc_s"] < min_active_ttc_s
            ):
                min_active_ttc_s = fact["ttc_s"]
        if peak_fact is None:
            peak_fact = fact
        else:
            current_rank = _SEVERITY_RANK.get(fact["severity"], 0)
            peak_rank = _SEVERITY_RANK.get(peak_fact["severity"], 0)
            if current_rank > peak_rank or (
                current_rank == peak_rank
                and fact["ttc_s"] is not None
                and (
                    peak_fact["ttc_s"] is None or fact["ttc_s"] < peak_fact["ttc_s"]
                )
            ):
                peak_fact = fact
        current_ttc_s = fact["ttc_s"]
        min_ttc_s = min_ttc_fact["ttc_s"] if min_ttc_fact is not None else None
        if current_ttc_s is not None and (
            min_ttc_s is None or current_ttc_s < min_ttc_s
        ):
            min_ttc_fact = fact

    if total_frames == 0 or first_fact is None or last_fact is None or peak_fact is None:
        return {
            "run_id": run_id,
            "total_frames": 0,
            "duration_s": 0.0,
            "peak_severity": "info",
            "peak_threat_level": "LOW",
            "active_alert_frames": 0,
            "active_alert_ratio": 0.0,
            "signal_trend": "stable",
            "highlights": [],
            "reasons_seen": [],
            "min_ttc_s": None,
            "min_ttc_during_alert_s": None,
        }

    highlights = _unique_highlights(
        [item for item in [first_fact, first_active_fact, peak_fact, min_ttc_fact, last_fact] if item is not None]
    )

    return {
        "run_id": run_id,
        "total_frames": total_frames,
        "duration_s": round(max(last_fact["time_s"] - first_fact["time_s"], 0.0), 2),
        "peak_severity": peak_fact["severity"],
        "peak_threat_level": peak_fact["threat_level"],
        "active_alert_frames": active_alert_frames,
        "active_alert_ratio": round(active_alert_frames / total_frames, 3),
        "signal_trend": _signal_trend(first_fact["rssi_db"], last_fact["rssi_db"]),
        "start_rssi_db": first_fact["rssi_db"],
        "end_rssi_db": last_fact["rssi_db"],
        "peak_rssi_db": peak_rssi_db,
        "min_ttc_s": min_ttc_fact["ttc_s"] if min_ttc_fact is not None else None,
        "min_ttc_during_alert_s": min_active_ttc_s,
        "first_alert_time_s": first_active_fact["time_s"] if first_active_fact is not None else None,
        "reasons_seen": sorted(reasons),
        "highlights": highlights,
    }


@router.get("/runs/{run_id}/ai_summary")
def ai_summary(run_id: str, request: Request) -> dict:
    if not ai_summaries_enabled():
        raise HTTPException(status_code=403, detail="AI summaries are disabled.")
    # Find the run directory
    recording = request.app.state.recording
    run_path = recording.runs_root / run_id
    if not run_path.is_dir():
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    reader = RunReader(run_path)
    run_facts = _build_run_facts(run_id, reader.iter_snapshots())
    summarizer = VertexAISummarizer()
    try:
        summary = summarizer.summarize_run(run_facts)
    except AISummaryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"summary": summary}

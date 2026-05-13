"""REST routes for runs, recording, and source control."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from kinetic_ranger.logging import RunReader

from .recording import (
    NotRecordingError,
    RecordingController,
    RecordingInProgressError,
)
from .schemas import (
    RecordingStartResponse,
    RecordingStatus,
    RecordingStopResponse,
    RunSummary,
    SeekRequest,
    SourceState,
    TimelinePoint,
)
from .simulation_service import (
    LiveFrameSource,
    ReplayFrameSource,
    SimulationService,
    frame_to_payload,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_SEVERITY_RANK = {"none": 0, "info": 1, "warning": 2, "critical": 3}
_RANK_TO_SEVERITY = {v: k for k, v in _SEVERITY_RANK.items()}


def _peak_severity(run_path: Path) -> str:
    """Scan snapshots.jsonl for the highest alert severity reached."""
    snapshots = run_path / "snapshots.jsonl"
    if not snapshots.exists():
        return "none"
    peak = 0
    try:
        with snapshots.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                alert = row.get("alert") or {}
                if not alert.get("active"):
                    continue
                severity = str(alert.get("severity", "info")).lower()
                rank = _SEVERITY_RANK.get(severity, 0)
                if rank > peak:
                    peak = rank
    except (OSError, json.JSONDecodeError):
        return "none"
    return _RANK_TO_SEVERITY.get(peak, "none")


def _load_manifest(run_path: Path) -> dict | None:
    manifest_path = run_path / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _resolve_run_dir(request: Request, run_id: str) -> Path:
    recording: RecordingController = request.app.state.recording
    candidate = recording.runs_root / run_id
    # Reject path traversal: the resolved path must stay inside runs_root.
    try:
        candidate_resolved = candidate.resolve(strict=False)
        root_resolved = recording.runs_root.resolve(strict=False)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if root_resolved not in candidate_resolved.parents and candidate_resolved != root_resolved:
        raise HTTPException(status_code=400, detail="invalid run_id")
    if not candidate.is_dir():
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    return candidate


def _source_state(request: Request) -> SourceState:
    source = request.app.state.frame_source
    if isinstance(source, ReplayFrameSource):
        return SourceState(
            mode="replay",
            source_run_id=source.run_id,
            replay_index=source.current_index,
            replay_tick_count=source.tick_count,
            paused=source.paused,
        )
    if isinstance(source, LiveFrameSource):
        return SourceState(mode="live")
    return SourceState(mode="simulation")


# ----- run listing & timeline -------------------------------------------------


@router.get("/runs", response_model=list[RunSummary])
def list_runs(request: Request) -> list[RunSummary]:
    recording: RecordingController = request.app.state.recording
    runs_root = recording.runs_root
    if not runs_root.exists():
        return []
    summaries: list[RunSummary] = []
    for entry in sorted(runs_root.iterdir(), key=lambda p: p.name, reverse=True):
        if not entry.is_dir():
            continue
        manifest = _load_manifest(entry)
        if manifest is None:
            continue
        summaries.append(
            RunSummary(
                run_id=entry.name,
                mode=str(manifest.get("mode", "unknown")),
                started_at_s=float(manifest.get("started_at_s", 0.0)),
                duration_s=float(manifest.get("duration_s", 0.0)),
                tick_count=int(manifest.get("tick_count", 0)),
                peak_severity=_peak_severity(entry),
            )
        )
    return summaries


@router.get("/runs/{run_id}/timeline", response_model=list[TimelinePoint])
def run_timeline(run_id: str, request: Request) -> list[TimelinePoint]:
    run_path = _resolve_run_dir(request, run_id)
    reader = RunReader(run_path)
    points: list[TimelinePoint] = []
    for frame_index, (observation, estimate, alert, _) in enumerate(reader.iter_snapshots()):
        del estimate  # only need timing + alert state
        severity = str(alert.severity).lower()
        threat_level = (
            "CRITICAL"
            if severity == "critical"
            else "HIGH"
            if severity == "warning"
            else "LOW"
            if severity == "info"
            else "NONE"
        )
        if not alert.active:
            threat_level = "NONE"
        points.append(
            TimelinePoint(
                frame=frame_index,
                time_s=observation.timestamp_s,
                threat_level=threat_level,
                alert_active=alert.active,
            )
        )
    return points


# ----- recording control ------------------------------------------------------


@router.get("/runs/record/status", response_model=RecordingStatus)
def recording_status(request: Request) -> RecordingStatus:
    return RecordingStatus(**request.app.state.recording.status())


@router.post("/runs/record/start", response_model=RecordingStartResponse)
def recording_start(request: Request) -> RecordingStartResponse:
    if isinstance(request.app.state.frame_source, ReplayFrameSource):
        raise HTTPException(
            status_code=409,
            detail="cannot record while a replay is active; switch to live first",
        )
    try:
        info = request.app.state.recording.start()
    except RecordingInProgressError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RecordingStartResponse(**info)


@router.post("/runs/record/stop", response_model=RecordingStopResponse)
def recording_stop(request: Request) -> RecordingStopResponse:
    try:
        info = request.app.state.recording.stop()
    except NotRecordingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RecordingStopResponse(**info)


# ----- source control ---------------------------------------------------------


@router.get("/source", response_model=SourceState)
def get_source(request: Request) -> SourceState:
    return _source_state(request)


@router.post("/runs/{run_id}/load", response_model=SourceState)
def load_run(run_id: str, request: Request) -> SourceState:
    run_path = _resolve_run_dir(request, run_id)
    if request.app.state.recording.is_recording:
        raise HTTPException(
            status_code=409,
            detail="stop the current recording before loading a replay",
        )
    config = request.app.state.config
    try:
        replay = ReplayFrameSource(config, run_path)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    request.app.state.frame_source = replay
    logger.info("Loaded replay source: %s", run_id)
    return _source_state(request)


@router.post("/source/live", response_model=SourceState)
def switch_to_live(request: Request) -> SourceState:
    """Swap to the hardware-backed ``LiveFrameSource``.

    Recording (if active) continues against the new source.
    Returns 409 if the SDR cannot be initialized — the caller stays where it was.
    """
    config = request.app.state.config
    try:
        live = LiveFrameSource(config)
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail=f"live source unavailable: {exc}",
        ) from exc
    request.app.state.frame_source = live
    logger.info("Switched to live SDR source")
    return _source_state(request)


@router.post("/source/sim", response_model=SourceState)
def switch_to_sim(request: Request) -> SourceState:
    """Swap to the synthetic ``SimulationService``. Always succeeds."""
    config = request.app.state.config
    request.app.state.frame_source = SimulationService(config)
    logger.info("Switched to synthetic source")
    return _source_state(request)


@router.post("/source/pause", response_model=SourceState)
def pause_source(request: Request) -> SourceState:
    source = request.app.state.frame_source
    if not isinstance(source, ReplayFrameSource):
        raise HTTPException(status_code=409, detail="only replay sources can be paused")
    source.paused = True
    return _source_state(request)


@router.post("/source/play", response_model=SourceState)
def play_source(request: Request) -> SourceState:
    source = request.app.state.frame_source
    if not isinstance(source, ReplayFrameSource):
        raise HTTPException(status_code=409, detail="only replay sources can be paused")
    source.paused = False
    return _source_state(request)


@router.post("/source/seek", response_model=SourceState)
def seek_source(body: SeekRequest, request: Request) -> SourceState:
    source = request.app.state.frame_source
    if not isinstance(source, ReplayFrameSource):
        raise HTTPException(status_code=409, detail="only replay sources can be seeked")
    frame = source.seek(body.frame)
    # Cache the seeked frame as the most recent one; pause/play decide whether
    # subsequent ticks advance from here. We don't transmit the frame here —
    # the next WS tick will pick it up via _last_frame.
    del frame  # already cached by seek()
    return _source_state(request)

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
    SimulationConfigRequest,
    SimulationControlRequest,
    SimulationStatus,
    SourceState,
    TimelinePoint,
)
from .simulation_service import (
    LiveFrameSource,
    ReplayFrameSource,
    SimulationService,
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


# ----- simulation control -----------------------------------------------------


def _require_sim(request: Request) -> "SimulationService":
    source = request.app.state.frame_source
    if not isinstance(source, SimulationService):
        raise HTTPException(
            status_code=409,
            detail="current source is not simulation; switch to SIM first",
        )
    return source


def _sim_status(source: "SimulationService", request: Request) -> SimulationStatus:
    cfg = request.app.state.config.simulation
    # Derived approach duration for drone-0 (canonical multiplier = 1.0).
    # Internal per-drone steps differ for multi-drone because each drone has a
    # range-multiplier applied to start_range_m.
    est_duration_s = round(
        max(cfg.start_range_m - cfg.end_range_m, 0.0) / max(cfg.speed_mps, 0.1), 1
    )
    return SimulationStatus(
        paused=source.paused,
        drone_count=cfg.drone_count,
        speed_mps=cfg.speed_mps,
        altitude_m=cfg.altitude_m,
        scenario=cfg.scenario,
        bursty=cfg.bursty,
        start_range_m=cfg.start_range_m,
        end_range_m=cfg.end_range_m,
        noise_std=cfg.noise_std,
        steps=cfg.steps,
        dt_s=cfg.dt_s,
        estimated_duration_s=est_duration_s,
    )


@router.get("/simulation/status", response_model=SimulationStatus)
def get_simulation_status(request: Request) -> SimulationStatus:
    source = _require_sim(request)
    return _sim_status(source, request)


@router.post("/simulation/control", response_model=SimulationStatus)
def simulation_control(body: SimulationControlRequest, request: Request) -> SimulationStatus:
    source = _require_sim(request)
    config = request.app.state.config
    if body.action == "pause":
        source.paused = True
    elif body.action == "start":
        source.paused = False
    elif body.action == "reset":
        request.app.state.frame_source = SimulationService(config)
        source = request.app.state.frame_source
    logger.info("Simulation control: action=%s", body.action)
    return _sim_status(source, request)


@router.post("/simulation/config", response_model=SimulationStatus)
def simulation_config_update(body: SimulationConfigRequest, request: Request) -> SimulationStatus:
    _require_sim(request)
    cfg = request.app.state.config.simulation
    # Pre-compute the effective values so we can validate BEFORE mutating the
    # config. This keeps the config clean if validation fails.
    new_start = max(10.0, min(2000.0, body.start_range_m)) if body.start_range_m is not None else cfg.start_range_m
    new_end = max(1.0, min(500.0, body.end_range_m)) if body.end_range_m is not None else cfg.end_range_m
    if new_start <= new_end:
        raise HTTPException(
            status_code=422,
            detail=f"start_range_m ({new_start}) must be greater than end_range_m ({new_end})",
        )
    # Validation passed — apply all changes.
    cfg.start_range_m = new_start
    cfg.end_range_m = new_end
    if body.noise_std is not None:
        cfg.noise_std = max(0.0, min(0.05, body.noise_std))
    if body.steps is not None:
        cfg.steps = max(5, min(500, body.steps))
    if body.dt_s is not None:
        cfg.dt_s = max(0.1, min(5.0, body.dt_s))
    if body.drone_count is not None:
        cfg.drone_count = max(1, min(10, body.drone_count))
    if body.speed_mps is not None:
        cfg.speed_mps = max(1.0, min(60.0, body.speed_mps))
    if body.altitude_m is not None:
        # 150 m is the practical upper bound: above this the RSSI slope at default
        # speed falls below the EKF's tti_slope_floor and TTC is never reported.
        cfg.altitude_m = max(0.0, min(150.0, body.altitude_m))
    if body.scenario is not None:
        cfg.scenario = body.scenario
    if body.bursty is not None:
        cfg.bursty = body.bursty
    request.app.state.frame_source = SimulationService(request.app.state.config)
    source = request.app.state.frame_source
    logger.info(
        "Simulation config updated: start_range_m=%s end_range_m=%s noise_std=%s",
        cfg.start_range_m,
        cfg.end_range_m,
        cfg.noise_std,
    )
    return _sim_status(source, request)

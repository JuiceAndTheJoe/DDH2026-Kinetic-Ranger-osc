/** REST client for the runs / recording / source-control endpoints. */

import type {
  RecordingStartResponse,
  RecordingStatus,
  RecordingStopResponse,
  RunSummary,
  SimulationStatus,
  SourceState,
  TimelinePoint,
} from "./types";

const API_BASE = "http://localhost:8000";

async function request<T>(
  method: "GET" | "POST",
  path: string,
  body?: unknown,
): Promise<T> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = (await res.json()) as { detail?: string };
      if (data?.detail) detail = data.detail;
    } catch {
      /* response body wasn't JSON */
    }
    throw new Error(`${method} ${path} failed: ${detail}`);
  }
  return (await res.json()) as T;
}

// ----- runs -------------------------------------------------------------------

export const listRuns = (): Promise<RunSummary[]> => request("GET", "/runs");

export const getTimeline = (runId: string): Promise<TimelinePoint[]> =>
  request("GET", `/runs/${encodeURIComponent(runId)}/timeline`);

// ----- recording --------------------------------------------------------------

export const getRecordingStatus = (): Promise<RecordingStatus> =>
  request("GET", "/runs/record/status");

export const startRecording = (): Promise<RecordingStartResponse> =>
  request("POST", "/runs/record/start");

export const stopRecording = (): Promise<RecordingStopResponse> =>
  request("POST", "/runs/record/stop");

// ----- source control ---------------------------------------------------------

export const getSource = (): Promise<SourceState> => request("GET", "/source");

export const loadRun = (runId: string): Promise<SourceState> =>
  request("POST", `/runs/${encodeURIComponent(runId)}/load`);

export const switchToLive = (): Promise<SourceState> =>
  request("POST", "/source/live");

export const switchToSim = (): Promise<SourceState> =>
  request("POST", "/source/sim");

export const pauseSource = (): Promise<SourceState> =>
  request("POST", "/source/pause");

export const playSource = (): Promise<SourceState> =>
  request("POST", "/source/play");

export const seekSource = (frame: number): Promise<SourceState> =>
  request("POST", "/source/seek", { frame });

// ----- simulation control -----------------------------------------------------

export const getSimulationStatus = (): Promise<SimulationStatus> =>
  request("GET", "/simulation/status");

export const simulationControl = (
  action: "start" | "pause" | "reset",
): Promise<SimulationStatus> =>
  request("POST", "/simulation/control", { action });

export const simulationConfig = (fields: {
  start_range_m?: number;
  end_range_m?: number;
  noise_std?: number;
  steps?: number;
  dt_s?: number;
  drone_count?: number;
  speed_mps?: number;
  altitude_m?: number;
}): Promise<SimulationStatus> =>
  request("POST", "/simulation/config", fields);

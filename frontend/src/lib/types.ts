/** Wire types for the /ws/radar WebSocket payload and REST API.
 *  Must stay in sync with src/kinetic_ranger/api/schemas.py. */

export type ThreatLevel = "CRITICAL" | "HIGH" | "LOW" | "NONE";

export type Mode = "simulation" | "replay" | "live";

export type ConnectionState =
  | "connecting"
  | "connected"
  | "disconnected"
  | "error";

export interface ReceiverInfo {
  id: string;
  label: string;
}

export interface TargetDisplay {
  bearing_deg: number;
  radial_ttc_norm: number; // 0 = far/unknown, 1 = impact imminent
}

export interface TargetState {
  id: string;
  rssi_db: number;
  rssi_slope_db_s: number;
  estimated_ttc_s: number; // -1.0 when time-to-contact is unavailable
  range_m: number;
  confidence: number;
  threat_level: ThreatLevel;
  closing: boolean;
  display: TargetDisplay;
}

export interface HistoryPoint {
  t: number;
  rssi: number;
}

export interface PayloadSummary {
  highest_threat: ThreatLevel;
  active_targets: number;
  alert: boolean;
}

export interface RadarPayload {
  mode: Mode;
  time_s: number;
  receiver: ReceiverInfo;
  targets: TargetState[];
  summary: PayloadSummary;
  source_run_id?: string | null;
  replay_index?: number | null;
  replay_tick_count?: number | null;
  paused?: boolean;
}

// ----- REST response shapes ---------------------------------------------------

export type Severity = "critical" | "warning" | "info" | "none";

export interface RunSummary {
  run_id: string;
  mode: string;
  started_at_s: number;
  duration_s: number;
  tick_count: number;
  peak_severity: Severity;
}

export interface TimelinePoint {
  frame: number;
  time_s: number;
  threat_level: ThreatLevel;
  alert_active: boolean;
}

export interface RecordingStatus {
  recording: boolean;
  run_id: string | null;
  started_at_s: number | null;
  tick_count: number;
}

export interface RecordingStartResponse {
  run_id: string;
  started_at_s: number;
}

export interface RecordingStopResponse {
  run_id: string;
  tick_count: number;
  duration_s: number;
  path: string;
}

export interface SourceState {
  mode: Mode;
  source_run_id: string | null;
  replay_index: number | null;
  replay_tick_count: number | null;
  paused: boolean;
}

export interface SimulationStatus {
  paused: boolean;
  drone_count: number;
  start_range_m: number;
  end_range_m: number;
  noise_std: number;
  steps: number;
  dt_s: number;
}

/** Wire types for the /ws/radar WebSocket payload. Must stay in sync with api/schemas.py. */

export type ThreatLevel = "CRITICAL" | "HIGH" | "LOW" | "NONE";

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
  mode: "simulation";
  time_s: number;
  receiver: ReceiverInfo;
  targets: TargetState[];
  summary: PayloadSummary;
}

import type { ConnectionState, PayloadSummary, ThreatLevel } from '../lib/types';

interface Props {
  summary: PayloadSummary | null;
  connectionState: ConnectionState;
}

const CONNECTION_LABELS: Record<ConnectionState, string> = {
  connecting: 'CONNECTING',
  connected: 'LIVE',
  disconnected: 'OFFLINE',
  error: 'ERROR',
};

export default function ThreatBanner({ summary, connectionState }: Props) {
  const threat: ThreatLevel = summary?.highest_threat ?? 'NONE';
  const alertActive = summary?.alert ?? false;
  const activeCount = summary?.active_targets ?? 0;

  return (
    <div className="threat-banner">
      <div className="threat-banner__connection" data-state={connectionState}>
        <span className="connection-dot" />
        <span className="connection-label">{CONNECTION_LABELS[connectionState]}</span>
      </div>

      <div className="threat-banner__title">
        KINETIC RANGER &mdash; PASSIVE RF THREAT DETECTION
      </div>

      <div className="threat-banner__status">
        <span className={`threat-badge threat-level--${threat.toLowerCase()}`}>
          {threat}
        </span>
        <span className="active-count">
          {activeCount} ACTIVE
        </span>
        {alertActive && <span className="alert-siren">&#9888;</span>}
      </div>
    </div>
  );
}

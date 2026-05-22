import type { TargetState } from '../lib/types';

interface Props {
  targets: TargetState[];
  timeS: number;
  mode: import('../lib/types').Mode | null;
}

function formatTtc(ttc: number): string {
  return ttc < 0 ? '—' : `${ttc.toFixed(1)}s`;
}

const COMPASS_POINTS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
function compassFor(bearingDeg: number): string {
  const normalized = ((bearingDeg % 360) + 360) % 360;
  const index = Math.round(normalized / 45) % 8;
  return COMPASS_POINTS[index];
}

export default function MetricsPanel({ targets, timeS, mode }: Props) {
  return (
    <div className="panel metrics-panel">
      <div className="panel-header">
        SIGNAL METRICS
        <span className="elapsed-time">T+{timeS.toFixed(1)}s</span>
      </div>

      {targets.length === 0 ? (
        <p className="no-targets">No targets detected</p>
      ) : (
        targets.map((t) => (
          <div key={t.id} className="target-row">
            <div className="target-id">{t.id.toUpperCase()}</div>
            <div className="metrics-grid">
              <div className="metric">
                <span className="metric-label">RANGE</span>
                <span className="metric-value">{t.range_m < 0 ? '—' : `${t.range_m.toFixed(0)} m`}</span>
              </div>
              {mode !== 'live' && (
              <div className="metric">
                <span className="metric-label">BEARING</span>
                <span className="metric-value">
                  <span
                    className="bearing-arrow"
                    style={{ transform: `rotate(${t.display.bearing_deg}deg)` }}
                    aria-hidden
                  >
                    ↑
                  </span>
                  {t.display.bearing_deg.toFixed(0)}°
                  <span className="bearing-cardinal">{compassFor(t.display.bearing_deg)}</span>
                </span>
              </div>
              )}
              <div className="metric">
                <span className="metric-label">RSSI</span>
                <span className="metric-value">{t.rssi_db.toFixed(1)} dBm</span>
              </div>
              <div className="metric">
                <span className="metric-label">SLOPE</span>
                <span
                  className="metric-value"
                  data-sign={t.rssi_slope_db_s > 0 ? 'pos' : 'neg'}
                >
                  {t.rssi_slope_db_s > 0 ? '+' : ''}
                  {t.rssi_slope_db_s.toFixed(2)} dB/s
                </span>
              </div>
              <div className="metric">
                <span className="metric-label">TTC</span>
                <span className="metric-value">{formatTtc(t.estimated_ttc_s)}</span>
              </div>
              <div className="metric">
                <span className="metric-label">CONFIDENCE</span>
                <span className="metric-value">
                  {(t.confidence * 100).toFixed(0)}%
                  <span
                    className="conf-bar"
                    style={{ width: `${(t.confidence * 100).toFixed(0)}%` }}
                  />
                </span>
              </div>
              <div className="metric">
                <span className="metric-label">THREAT</span>
                <span className={`threat-badge threat-level--${t.threat_level.toLowerCase()}`}>
                  {t.threat_level}
                </span>
              </div>
              <div className="metric">
                <span className="metric-label">STATUS</span>
                <span className="metric-value" data-closing={t.closing}>
                  {t.closing ? '▼ CLOSING' : '— STATIC'}
                </span>
              </div>
              <div className="metric">
                <span className="metric-label">SIM ALT</span>
                <span className="metric-value metric-value--meta">
                  {t.altitude_m != null ? `${t.altitude_m.toFixed(0)} m` : '—'}
                </span>
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

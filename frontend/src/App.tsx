import { useEffect, useRef, useState } from 'react';
import './App.css';
import MetricsPanel from './components/MetricsPanel';
import RadarView from './components/RadarView';
import RecordButton from './components/RecordButton';
import ReplayScrubber from './components/ReplayScrubber';
import RunsPanel from './components/RunsPanel';
import SignalGraph from './components/SignalGraph';
import SimulationControls from './components/SimulationControls';
import SourceSelector from './components/SourceSelector';
import ThreatBanner from './components/ThreatBanner';
import { RadarWebSocket } from './lib/websocket';
import type { ConnectionState, HistoryPoint, RadarPayload, TargetState } from './lib/types';

const _THREAT_RANK: Record<string, number> = {
  CRITICAL: 3, HIGH: 2, LOW: 1, NONE: 0,
};

/** Pick the highest-threat target; break ties by shortest positive TTC. */
function pickPrimary(targets: TargetState[]): TargetState | null {
  if (targets.length === 0) return null;
  return [...targets].sort((a, b) => {
    const rankDiff =
      (_THREAT_RANK[b.threat_level] ?? 0) - (_THREAT_RANK[a.threat_level] ?? 0);
    if (rankDiff !== 0) return rankDiff;
    const aTtc = a.estimated_ttc_s < 0 ? Infinity : a.estimated_ttc_s;
    const bTtc = b.estimated_ttc_s < 0 ? Infinity : b.estimated_ttc_s;
    return aTtc - bTtc;
  })[0];
}

const WS_URL = 'ws://localhost:8000/ws/radar';
const MAX_HISTORY = 60;
const TOAST_MS = 3500;

export default function App() {
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [payload, setPayload] = useState<RadarPayload | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [runsRefreshKey, setRunsRefreshKey] = useState(0);
  const [toast, setToast] = useState<string | null>(null);
  const wsRef = useRef<RadarWebSocket | null>(null);
  const toastTimerRef = useRef<number | null>(null);

  useEffect(() => {
    const ws = new RadarWebSocket(
      WS_URL,
      (nextPayload) => {
        setPayload(nextPayload);
        const target = pickPrimary(nextPayload.targets);
        if (!target) {
          return;
        }

        setHistory((prev) => {
          const next = [...prev, { t: Date.now() / 1000, rssi: target.rssi_db }];
          return next.slice(-MAX_HISTORY);
        });
      },
      setConnectionState,
    );
    wsRef.current = ws;
    ws.connect();
    return () => {
      ws.disconnect();
    };
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current !== null) {
        clearTimeout(toastTimerRef.current);
      }
    };
  }, []);

  const showToast = (text: string) => {
    setToast(text);
    if (toastTimerRef.current !== null) {
      clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = window.setTimeout(() => setToast(null), TOAST_MS);
  };

  const mode = payload?.mode ?? null;
  const sourceRunId = payload?.source_run_id ?? null;
  const replayIndex = payload?.replay_index ?? null;
  const replayTickCount = payload?.replay_tick_count ?? null;
  const paused = payload?.paused ?? false;

  useEffect(() => {
    document.body.dataset.mode = mode ?? 'simulation';
    return () => {
      delete document.body.dataset.mode;
    };
  }, [mode]);

  const showScrubber =
    mode === 'replay' &&
    sourceRunId !== null &&
    replayTickCount !== null &&
    replayTickCount > 0;

  return (
    <div className="dashboard" data-mode={mode ?? 'simulation'}>
      <ThreatBanner
        summary={payload?.summary ?? null}
        connectionState={connectionState}
        mode={mode}
      />

      <div className="dashboard-main">
        <div className="dashboard-rail">
          <div className="panel">
            <div className="panel-header">SOURCE</div>
            <SourceSelector mode={mode} onMessage={showToast} />
          </div>
          <div className="panel">
            <div className="panel-header">CAPTURE RUN</div>
            <RecordButton
              mode={mode}
              onRecordingStopped={() => setRunsRefreshKey((k) => k + 1)}
              onMessage={showToast}
            />
          </div>
          <RunsPanel
            activeRunId={sourceRunId}
            refreshKey={runsRefreshKey}
            onMessage={showToast}
          />
        </div>

        <div className="dashboard-left">
          <RadarView targets={payload?.targets ?? []} />
          {showScrubber && (
            <ReplayScrubber
              runId={sourceRunId!}
              currentFrame={replayIndex ?? 0}
              tickCount={replayTickCount!}
              paused={paused}
              onMessage={showToast}
            />
          )}
        </div>

        <div className="dashboard-right">
          <MetricsPanel
            targets={payload?.targets ?? []}
            timeS={payload?.time_s ?? 0}
          />
          <SignalGraph history={history} />
          <SimulationControls />
        </div>
      </div>

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}

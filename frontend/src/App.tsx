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
import { WS_URL } from './lib/config';
import { RadarWebSocket } from './lib/websocket';
import {
  DEFAULT_DT_S,
  DEFAULT_SCENARIO,
  createGeneratorState,
  generateMockFrame,
  getScenario,
  type ScenarioId,
} from './lib/scenarios';
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

const MAX_HISTORY = 60;
const TOAST_MS = 3500;
const MOCK_TICK_MS = DEFAULT_DT_S * 1000;

export default function App() {
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [livePayload, setLivePayload] = useState<RadarPayload | null>(null);
  const [mockPayload, setMockPayload] = useState<RadarPayload | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [runsRefreshKey, setRunsRefreshKey] = useState(0);
  const [toast, setToast] = useState<string | null>(null);
  const [scenario, setScenario] = useState<ScenarioId>(DEFAULT_SCENARIO);
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const wsRef = useRef<RadarWebSocket | null>(null);
  const toastTimerRef = useRef<number | null>(null);

  // Mock-scenario player. Active only when a non-default scenario is picked
  // AND the underlying source is simulation (mocks shouldn't override live SDR
  // or recorded replays — those carry real or replayed data).
  const activeScenario = getScenario(scenario);
  const isMockActive =
    activeScenario.kind === 'mock' &&
    (livePayload?.mode ?? 'simulation') === 'simulation';

  // Ref mirror so the long-lived WS subscription can read the current value
  // without re-binding the socket every time the user picks a different
  // scenario.
  const isMockActiveRef = useRef(isMockActive);
  useEffect(() => {
    isMockActiveRef.current = isMockActive;
  }, [isMockActive]);

  function pushHistory(rssiDb: number) {
    setHistory((prev) => {
      const next = [...prev, { t: Date.now() / 1000, rssi: rssiDb }];
      return next.slice(-MAX_HISTORY);
    });
  }

  useEffect(() => {
    const ws = new RadarWebSocket(
      WS_URL,
      (nextPayload) => {
        setLivePayload(nextPayload);
        // History only follows live data when we're not running a mock.
        if (isMockActiveRef.current) return;
        const target = pickPrimary(nextPayload.targets);
        if (target) pushHistory(target.rssi_db);
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
    if (!isMockActive) return undefined;
    const state = createGeneratorState();
    let tick = 0;
    const emit = () => {
      const frame = generateMockFrame(
        scenario,
        tick * DEFAULT_DT_S,
        DEFAULT_DT_S,
        state,
      );
      setMockPayload(frame);
      const target = frame.targets[0];
      if (target) pushHistory(target.rssi_db);
      tick += 1;
    };
    emit();
    const handle = window.setInterval(emit, MOCK_TICK_MS);
    return () => {
      window.clearInterval(handle);
    };
  }, [isMockActive, scenario]);

  // When the active source changes (live ↔ mock, or scenario swap) the old
  // mockPayload is stale; gating on isMockActive at the selector below means
  // we never display it, but clearing it keeps DevTools state tidy.
  const payload = isMockActive ? mockPayload : livePayload;

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

  // The picker only makes sense when the underlying source is sim-shaped.
  // Live SDR and replays own their own data; we don't want users selecting
  // "Hover" while watching a recorded approach and getting nothing.
  const scenarioPickerDisabled =
    livePayload !== null && livePayload.mode !== 'simulation';

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
      <RadarView targets={payload?.targets ?? []} mode={mode} />

      <ThreatBanner
        summary={payload?.summary ?? null}
        connectionState={connectionState}
        mode={mode}
      />

      <button
        type="button"
        className={`dashboard-rail__toggle${railCollapsed ? ' dashboard-rail__toggle--collapsed' : ''}`}
        onClick={() => setRailCollapsed((c) => !c)}
        aria-label={railCollapsed ? 'Show side panel' : 'Hide side panel'}
        aria-expanded={!railCollapsed}
        title={railCollapsed ? 'Show side panel' : 'Hide side panel'}
      >
        <span aria-hidden="true">{railCollapsed ? '›' : '‹'}</span>
      </button>
      <div
        className={`dashboard-rail${railCollapsed ? ' dashboard-rail--collapsed' : ''}`}
        aria-hidden={railCollapsed}
      >
        <div className="panel panel--transparent">
          <div className="panel-header">SOURCE</div>
          <SourceSelector mode={mode} onMessage={showToast} />
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

      <button
        type="button"
        className={`dashboard-right__toggle${rightCollapsed ? ' dashboard-right__toggle--collapsed' : ''}`}
        onClick={() => setRightCollapsed((c) => !c)}
        aria-label={rightCollapsed ? 'Show metrics panel' : 'Hide metrics panel'}
        aria-expanded={!rightCollapsed}
        title={rightCollapsed ? 'Show metrics panel' : 'Hide metrics panel'}
      >
        <span aria-hidden="true">{rightCollapsed ? '‹' : '›'}</span>
      </button>
      <div
        className={`dashboard-right${rightCollapsed ? ' dashboard-right--collapsed' : ''}`}
        aria-hidden={rightCollapsed}
      >
        <MetricsPanel
          targets={payload?.targets ?? []}
          timeS={payload?.time_s ?? 0}
          mode={mode}
        />
        <SignalGraph history={history} />
        {mode !== 'live' && (
          <SimulationControls
            scenario={scenario}
            onScenarioChange={setScenario}
            disabledReason={
              scenarioPickerDisabled
                ? 'Scenario picker only applies to simulation source'
                : null
            }
          />
        )}
      </div>

      {showScrubber && (
        <ReplayScrubber
          runId={sourceRunId!}
          currentFrame={replayIndex ?? 0}
          tickCount={replayTickCount!}
          paused={paused}
          onMessage={showToast}
        />
      )}

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}

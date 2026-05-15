import { useEffect, useState } from 'react';
import { listRuns, loadRun, switchToLive, getAiSummary } from '../lib/runsApi';
import type { RunSummary } from '../lib/types';

interface Props {
  activeRunId: string | null;
  refreshKey?: number;
  onMessage?: (text: string) => void;
}

export default function RunsPanel({ activeRunId, refreshKey, onMessage }: Props) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [summaries, setSummaries] = useState<Record<string, string>>({});
  const [loadingSummary, setLoadingSummary] = useState<Record<string, boolean>>({});

  useEffect(() => {
    async function fetch() {
      try {
        const data = await listRuns();
        setRuns(data);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        if (onMessage) onMessage(`Runs fetch failed: ${msg}`);
        else console.warn('RunsPanel: listRuns error', err);
      }
    }
    fetch();
  }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleRefresh() {
    try {
      const data = await listRuns();
      setRuns(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (onMessage) onMessage(`Runs fetch failed: ${msg}`);
      else console.warn('RunsPanel: listRuns error', err);
    }
  }

  async function handleLive() {
    try {
      await switchToLive();
      if (onMessage) onMessage('Switched to live source.');
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (onMessage) onMessage(`Switch to live failed: ${msg}`);
      else console.warn('RunsPanel: switchToLive error', err);
    }
  }

  async function handleLoad(runId: string) {
    try {
      await loadRun(runId);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (onMessage) onMessage(`Load run failed: ${msg}`);
      else console.warn('RunsPanel: loadRun error', err);
    }
  }

  async function handleAiSummary(e: React.MouseEvent, runId: string) {
    e.stopPropagation();
    if (summaries[runId]) {
      // Toggle off if already loaded
      setSummaries(prev => { const next = { ...prev }; delete next[runId]; return next; });
      return;
    }
    setLoadingSummary(prev => ({ ...prev, [runId]: true }));
    try {
      const res = await getAiSummary(runId);
      setSummaries(prev => ({ ...prev, [runId]: res.summary }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setSummaries(prev => ({ ...prev, [runId]: `Error: ${msg}` }));
    } finally {
      setLoadingSummary(prev => ({ ...prev, [runId]: false }));
    }
  }

  return (
    <div className="panel runs-panel">
      <div className="panel-header">
        <span>RECORDED RUNS</span>
        <div className="runs-panel__header-row" style={{ marginLeft: 'auto' }}>
          <button className="runs-panel__live" onClick={handleLive}>← Live</button>
          <button className="runs-panel__refresh" onClick={handleRefresh}>↻</button>
        </div>
      </div>

      {runs.length === 0 ? (
        <div className="runs-panel__empty">No runs yet — hit ● REC.</div>
      ) : (
        runs.map(run => (
          <div key={run.run_id} className="run-card-wrapper">
            <button
              className={`run-card ${run.run_id === activeRunId ? 'run-card--active' : ''}`}
              onClick={() => handleLoad(run.run_id)}
            >
              <span className="run-card__title">{run.run_id}</span>
              <span className="run-card__meta">
                <span>{run.tick_count} ticks</span>
                <span>{run.duration_s.toFixed(1)}s</span>
                <span>{run.peak_severity.toUpperCase()}</span>
              </span>
              <div className="run-card__bar" data-severity={run.peak_severity} />
            </button>
            <button
              className="run-card__ai-btn"
              title="AI summary"
              onClick={e => handleAiSummary(e, run.run_id)}
              disabled={loadingSummary[run.run_id]}
            >
              {loadingSummary[run.run_id] ? '…' : summaries[run.run_id] ? '✕' : '✦ AI'}
            </button>
            {summaries[run.run_id] && (
              <div className="run-card__ai-summary">
                {summaries[run.run_id]}
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
}

import { useState } from 'react';
import { switchToLive, switchToSim } from '../lib/runsApi';
import type { Mode } from '../lib/types';

interface Props {
  mode: Mode | null;
  onMessage?: (text: string) => void;
}

/**
 * Two-segment SOURCE selector. Visual states:
 *   - mode === 'live'       → LIVE highlighted + "● connected"
 *   - mode === 'simulation' → SIM highlighted  + LIVE shows "○ not connected"
 *                              (last known state; clicking LIVE attempts a probe)
 *   - mode === 'replay'     → neither segment highlighted; clicking either
 *                              exits replay to that source
 *
 * "Connected" is defined as "the active source IS the live hardware". We do
 * not background-probe the device — the user discovers connectivity by
 * clicking LIVE, which either succeeds (now we know) or 409s with the reason.
 */
export default function SourceSelector({ mode, onMessage }: Props) {
  const [busy, setBusy] = useState(false);

  const liveConnected = mode === 'live';
  const inReplay = mode === 'replay';
  const simActive = mode === 'simulation';

  const notify = (text: string) => {
    if (onMessage) onMessage(text);
    else console.log(text);
  };

  async function handleClick(target: 'sim' | 'live') {
    if (busy) return;
    setBusy(true);
    try {
      if (target === 'live') {
        try {
          await switchToLive();
          notify('Switched to live SDR.');
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          notify(`Live unavailable: ${msg}`);
        }
      } else {
        try {
          await switchToSim();
          notify('Switched to simulation.');
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          notify(`Sim swap failed: ${msg}`);
        }
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="source-selector">
      <div className="source-selector__segments" role="group" aria-label="Source selector">
        <button
          type="button"
          className={`source-segment ${simActive ? 'source-segment--active' : ''}`}
          onClick={() => handleClick('sim')}
          disabled={busy}
        >
          <span className="source-segment__label">SIM</span>
          <span className="source-segment__sub">synthetic</span>
        </button>
        <button
          type="button"
          className={`source-segment source-segment--live ${liveConnected ? 'source-segment--active' : ''}`}
          onClick={() => handleClick('live')}
          disabled={busy}
        >
          <span className="source-segment__label">LIVE</span>
          <span
            className={`source-segment__sub ${liveConnected ? 'source-segment__sub--ok' : 'source-segment__sub--off'}`}
          >
            {liveConnected ? '● connected' : '○ not connected'}
          </span>
        </button>
      </div>
      {inReplay && (
        <p className="source-selector__hint">
          Currently replaying a recording. Pick SIM or LIVE to exit replay.
        </p>
      )}
    </div>
  );
}

import { useEffect, useState } from 'react';
import {
  SCENARIOS,
  getScenario,
  type ScenarioId,
} from '../lib/scenarios';
import {
  getSimulationStatus,
  simulationConfig,
  simulationControl,
} from '../lib/runsApi';
import type { SimulationStatus } from '../lib/types';

/**
 * UI scaffold — only the scenario picker is wired (it drives an in-app mock
 * generator). Drone-count / altitude / speed / noise / start/pause/reset are
 * still visual placeholders. When `/simulation/control` and
 * `/simulation/config` are added in the backend, wire those here.
 */

interface Props {
  scenario: ScenarioId;
  onScenarioChange: (next: ScenarioId) => void;
  disabledReason: string | null;
}

export default function SimulationControls({
  scenario,
  onScenarioChange,
  disabledReason,
}: Props) {
  const [droneCount, setDroneCount] = useState(1);
  const [altitude, setAltitude] = useState(80);
  const [speed, setSpeed] = useState(12);
  const [startDistance, setStartDistance] = useState(220);
  const [noiseLevel, setNoiseLevel] = useState(0.0005);
  const [bursty, setBursty] = useState(false);

  const [isRunning, setIsRunning] = useState(true);
  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [simStatus, setSimStatus] = useState<SimulationStatus | null>(null);
  const [notInSim, setNotInSim] = useState(false);

  // Sync all form controls AND meta-state from a backend SimulationStatus.
  // Call this after any operation that may have changed config values (apply,
  // mount). Do NOT call this for pause/start/reset — those don't change config.
  function syncControls(s: SimulationStatus) {
    setSimStatus(s);
    setIsRunning(!s.paused);
    setDroneCount(s.drone_count);
    setSpeed(s.speed_mps);
    setAltitude(s.altitude_m);
    onScenarioChange(s.scenario as ScenarioId);
    setBursty(s.bursty);
    setStartDistance(s.start_range_m);
    setNoiseLevel(s.noise_std);
    setNotInSim(false);
  }

  // Sync state from backend on mount
  useEffect(() => {
    getSimulationStatus()
      .then(syncControls)
      .catch(() => {
        // 409 = source is not sim; show a note but keep UI rendered
        setNotInSim(true);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Used by pause/start/reset — config values unchanged, only meta-state updates.
  function applyStatus(s: SimulationStatus) {
    setSimStatus(s);
    setIsRunning(!s.paused);
    setNotInSim(false);
  }

  async function handleStartPause() {
    if (busy) return;
    const action = isRunning ? 'pause' : 'start';
    setBusy(true);
    setStatusMsg(null);
    try {
      const s = await simulationControl(action);
      applyStatus(s);
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleReset() {
    if (busy) return;
    setBusy(true);
    setStatusMsg(null);
    try {
      const s = await simulationControl('reset');
      applyStatus(s);
      setStatusMsg('Simulation reset.');
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleApplyConfig() {
    if (busy) return;
    setBusy(true);
    setStatusMsg(null);
    try {
      const s = await simulationConfig({
        start_range_m: startDistance,
        noise_std: noiseLevel,
        drone_count: droneCount,
        speed_mps: speed,
        altitude_m: altitude,
        scenario,
        bursty,
      });
      // Sync controls from backend-confirmed (possibly clamped) values.
      syncControls(s);
      setStatusMsg('Config applied — simulation restarted.');
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const pickerDisabled = disabledReason !== null;
  const activeScenario = getScenario(scenario);

  return (
    <div className="panel sim-controls">
      <div className="panel-header">SIMULATION CONTROLS</div>

      <div className="scenario-picker">
        <label htmlFor="scenario-select" className="scenario-picker__label">
          Scenario
        </label>
        {/* `kind: 'mock'` scenarios are scripted in `lib/scenarios.ts` and
            don't reach the backend — operators don't need to know that
            distinction in the UI, so we render every entry uniformly. */}
        <select
          id="scenario-select"
          value={scenario}
          onChange={(e) => onScenarioChange(e.target.value as ScenarioId)}
          disabled={pickerDisabled}
          className="ctrl-input scenario-picker__select"
        >
          {SCENARIOS.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
        <p className="scenario-picker__description">
          {pickerDisabled ? disabledReason : activeScenario.description}
        </p>
      </div>
      {notInSim && (
        <p className="sim-status sim-status--warn">
          ⚠ Switch source to SIM to use controls.
        </p>
      )}

      <div className="controls-grid">
        <label className="ctrl-label">
          Drones
          <input
            type="number"
            min={1}
            max={10}
            value={droneCount}
            onChange={(e) => setDroneCount(Number(e.target.value))}
            className="ctrl-input"
          />
        </label>

        <label className="ctrl-label">
          Sim Altitude (m)
          <input
            type="number"
            min={0}
            max={150}
            value={altitude}
            onChange={(e) => setAltitude(Number(e.target.value))}
            className="ctrl-input"
          />
        </label>

        <label className="ctrl-label">
          Sim Speed (m/s)
          <input
            type="number"
            min={1}
            max={60}
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
            className="ctrl-input"
          />
        </label>

        <label className="ctrl-label">
          Sim Start Dist (m)
          <input
            type="number"
            min={10}
            max={2000}
            value={startDistance}
            onChange={(e) => setStartDistance(Number(e.target.value))}
            className="ctrl-input"
          />
        </label>

        <label className="ctrl-label">
          Noise
          <input
            type="range"
            min={0}
            max={0.005}
            step={0.0001}
            value={noiseLevel}
            onChange={(e) => setNoiseLevel(Number(e.target.value))}
            className="ctrl-range"
          />
        </label>

        <label className="ctrl-label ctrl-label--toggle">
          Bursty TX
          <input
            type="checkbox"
            checked={bursty}
            onChange={(e) => setBursty(e.target.checked)}
            className="ctrl-checkbox"
            disabled
            title="Bursty transmission simulation is not yet implemented."
          />
          <span className="ctrl-hint">Coming later</span>
        </label>
      </div>

      <div className="ctrl-buttons">
        <button
          className={`ctrl-btn ctrl-btn--${isRunning ? 'pause' : 'start'}`}
          onClick={handleStartPause}
          disabled={busy || notInSim}
        >
          {isRunning ? '⏸ PAUSE' : '▶ START'}
        </button>
        <button
          className="ctrl-btn ctrl-btn--reset"
          onClick={handleReset}
          disabled={busy || notInSim}
        >
          ↺ RESET
        </button>
        <button
          className="ctrl-btn ctrl-btn--apply"
          onClick={handleApplyConfig}
          disabled={busy || notInSim}
        >
          ✓ APPLY
        </button>
      </div>

      <p className="sim-status">
        {statusMsg
          ? statusMsg
          : isRunning
            ? '● SIMULATION RUNNING'
            : '○ SIMULATION PAUSED'}
      </p>

      {simStatus && (
        <p className="sim-config-info">
          {simStatus.start_range_m.toFixed(0)} m → {simStatus.end_range_m.toFixed(0)} m
          &nbsp;·&nbsp; {simStatus.speed_mps.toFixed(0)} m/s
          &nbsp;·&nbsp; ~{simStatus.estimated_duration_s.toFixed(1)}s/loop
          &nbsp;·&nbsp; alt {simStatus.altitude_m.toFixed(0)} m
          &nbsp;·&nbsp; noise {simStatus.noise_std.toFixed(4)}
        </p>
      )}
    </div>
  );
}

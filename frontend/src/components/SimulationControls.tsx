import { useState } from 'react';
import {
  SCENARIOS,
  getScenario,
  type ScenarioId,
} from '../lib/scenarios';

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
  const [altitude, setAltitude] = useState(50);
  const [speed, setSpeed] = useState(15);
  const [startDistance, setStartDistance] = useState(220);
  const [noiseLevel, setNoiseLevel] = useState(0.0005);
  const [bursty, setBursty] = useState(false);
  const [isRunning, setIsRunning] = useState(true);

  const handleStartPause = () => {
    setIsRunning((r) => !r);
    // TODO: POST /simulation/control { action: isRunning ? 'pause' : 'start' }
  };

  const handleReset = () => {
    setIsRunning(false);
    // TODO: POST /simulation/control { action: 'reset' }
  };

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
          Altitude (m)
          <input
            type="number"
            min={0}
            max={400}
            value={altitude}
            onChange={(e) => setAltitude(Number(e.target.value))}
            className="ctrl-input"
          />
        </label>

        <label className="ctrl-label">
          Speed (m/s)
          <input
            type="number"
            min={0}
            max={50}
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
            className="ctrl-input"
          />
        </label>

        <label className="ctrl-label">
          Start Dist (m)
          <input
            type="number"
            min={10}
            max={1000}
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
          />
        </label>
      </div>

      <div className="ctrl-buttons">
        <button
          className={`ctrl-btn ctrl-btn--${isRunning ? 'pause' : 'start'}`}
          onClick={handleStartPause}
        >
          {isRunning ? '⏸ PAUSE' : '▶ START'}
        </button>
        <button className="ctrl-btn ctrl-btn--reset" onClick={handleReset}>
          ↺ RESET
        </button>
      </div>

      <p className="sim-status">
        {isRunning ? '● SIMULATION RUNNING' : '○ SIMULATION PAUSED'}
      </p>
    </div>
  );
}

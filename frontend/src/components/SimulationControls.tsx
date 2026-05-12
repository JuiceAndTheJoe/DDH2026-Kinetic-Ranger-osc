import { useState } from 'react';

/**
 * UI scaffold only — controls are not yet wired to the backend.
 * TODO: POST { action: 'start' | 'pause' | 'reset' } to /simulation/control
 * TODO: POST { drone_count, altitude_m, speed_mps, ... } to /simulation/config
 * Both endpoints should be added to kinetic_ranger/api/main.py when ready.
 */

type ScenarioType = 'approach' | 'flyby' | 'hover';

export default function SimulationControls() {
  const [droneCount, setDroneCount] = useState(1);
  const [altitude, setAltitude] = useState(50);
  const [speed, setSpeed] = useState(15);
  const [startDistance, setStartDistance] = useState(220);
  const [scenario, setScenario] = useState<ScenarioType>('approach');
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

  return (
    <div className="panel sim-controls">
      <div className="panel-header">SIMULATION CONTROLS</div>

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
          Scenario
          <select
            value={scenario}
            onChange={(e) => setScenario(e.target.value as ScenarioType)}
            className="ctrl-input"
          >
            <option value="approach">Direct Approach</option>
            <option value="flyby">Fly-by</option>
            <option value="hover">Hover</option>
          </select>
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

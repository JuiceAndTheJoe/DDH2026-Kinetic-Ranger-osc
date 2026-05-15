/**
 * Scenario catalog for the simulation playback picker.
 *
 * Only `direct_approach` is backed by the real backend pipeline today.
 * Every other entry is a frontend-only mockup: the generator below produces
 * fully-shaped `RadarPayload` frames so the UI can be demoed end-to-end
 * without any backend changes. Promote a scenario from mock to real by
 * implementing the trajectory in the backend (see `radio/capture.py`) and
 * flipping `kind: 'mock'` → `kind: 'live'` here.
 */
import type { RadarPayload, TargetState, ThreatLevel } from './types';

export type ScenarioId =
  | 'direct_approach'
  | 'flyby'
  | 'hover'
  | 'loiter_orbit'
  | 'bursty_comms'
  | 'evasive_zigzag';

export type ScenarioKind = 'live' | 'mock';

export interface ScenarioDef {
  id: ScenarioId;
  label: string;
  description: string;
  kind: ScenarioKind;
}

export const SCENARIOS: ScenarioDef[] = [
  {
    id: 'direct_approach',
    label: 'Direct Approach',
    description: 'Single emitter closing radially toward the receiver.',
    kind: 'live',
  },
  {
    id: 'flyby',
    label: 'Fly-by',
    description: 'Target closes to CPA, then recedes past the receiver.',
    kind: 'mock',
  },
  {
    id: 'hover',
    label: 'Hover',
    description: 'Stationary emitter, near-constant RSSI with light noise.',
    kind: 'mock',
  },
  {
    id: 'loiter_orbit',
    label: 'Loiter / Orbit',
    description: 'Slow circular loiter — bearing sweeps, range oscillates.',
    kind: 'mock',
  },
  {
    id: 'bursty_comms',
    label: 'Bursty Comms',
    description: 'Closing target with intermittent transmit windows.',
    kind: 'mock',
  },
  {
    id: 'evasive_zigzag',
    label: 'Evasive Zig-zag',
    description: 'Closing target with bearing/range jitter and lower confidence.',
    kind: 'mock',
  },
];

const SCENARIO_BY_ID: Record<ScenarioId, ScenarioDef> = SCENARIOS.reduce(
  (acc, s) => {
    acc[s.id] = s;
    return acc;
  },
  {} as Record<ScenarioId, ScenarioDef>,
);

export function getScenario(id: ScenarioId): ScenarioDef {
  return SCENARIO_BY_ID[id];
}

export const DEFAULT_SCENARIO: ScenarioId = 'direct_approach';

/** ---- Generators ---------------------------------------------------------- */

const RECEIVER = { id: 'station-1', label: 'Passive RF Sensor (mock)' };
const TTI_THRESHOLD_S = 12.0;
const PATH_LOSS_EXPONENT = 2.15;
const EFFECTIVE_POWER_DB = -6.0;

function rssiFromRange(rangeM: number, noise: number = 0): number {
  const r = Math.max(rangeM, 1.0);
  return EFFECTIVE_POWER_DB - 10.0 * PATH_LOSS_EXPONENT * Math.log10(r) + noise;
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

function threatFromTtc(ttcS: number, closing: boolean): ThreatLevel {
  if (!closing || ttcS < 0) return 'NONE';
  if (ttcS < 4) return 'CRITICAL';
  if (ttcS < TTI_THRESHOLD_S) return 'HIGH';
  if (ttcS < TTI_THRESHOLD_S * 2) return 'LOW';
  return 'NONE';
}

function buildPayload(opts: {
  scenario: ScenarioId;
  timeS: number;
  rangeM: number;
  bearingDeg: number;
  closingMps: number;
  rssiDb: number;
  rssiSlope: number;
  confidence: number;
  emitting?: boolean;
}): RadarPayload {
  const {
    scenario,
    timeS,
    rangeM,
    bearingDeg,
    closingMps,
    rssiDb,
    rssiSlope,
    confidence,
    emitting = true,
  } = opts;

  const closing = closingMps < -0.1;
  const ttcS = closing ? rangeM / Math.abs(closingMps) : -1;
  const threat: ThreatLevel = emitting ? threatFromTtc(ttcS, closing) : 'NONE';
  const radialTtcNorm =
    ttcS > 0 ? clamp(1 - ttcS / TTI_THRESHOLD_S, 0, 1) : 0;

  const target: TargetState = {
    id: `${scenario}-1`,
    rssi_db: Number(rssiDb.toFixed(2)),
    rssi_slope_db_s: Number(rssiSlope.toFixed(3)),
    estimated_ttc_s: Number((ttcS < 0 ? -1 : ttcS).toFixed(2)),
    range_m: Number(rangeM.toFixed(1)),
    confidence: Number(clamp(confidence, 0, 1).toFixed(3)),
    threat_level: threat,
    closing,
    display: {
      bearing_deg: Number(((bearingDeg % 360) + 360) % 360),
      radial_ttc_norm: Number(radialTtcNorm.toFixed(3)),
    },
  };

  const alertActive = threat === 'CRITICAL' || threat === 'HIGH';

  return {
    mode: 'simulation',
    time_s: Number(timeS.toFixed(2)),
    receiver: RECEIVER,
    targets: emitting ? [target] : [],
    summary: {
      highest_threat: emitting ? threat : 'NONE',
      active_targets: emitting ? 1 : 0,
      alert: alertActive,
    },
    source_run_id: null,
    replay_index: null,
    replay_tick_count: null,
    paused: false,
  };
}

interface GeneratorState {
  prevRssi: number | null;
}

export function createGeneratorState(): GeneratorState {
  return { prevRssi: null };
}

/** Default sim cadence — matches backend SimulationConfig.dt_s. */
export const DEFAULT_DT_S = 0.5;

/** Loop length per scenario (seconds). Picked so demos cycle cleanly. */
const LOOP_S: Record<Exclude<ScenarioId, 'direct_approach'>, number> = {
  flyby: 30,
  hover: 24,
  loiter_orbit: 32,
  bursty_comms: 30,
  evasive_zigzag: 24,
};

function jitter(seed: number, amp: number): number {
  // Cheap deterministic-ish wobble — small amplitude, no Math.random across
  // re-renders (we *want* per-tick variation here, but stable per (seed, amp)).
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return (x - Math.floor(x) - 0.5) * 2 * amp;
}

function flybyFrame(t: number): Omit<
  Parameters<typeof buildPayload>[0],
  'scenario' | 'rssiSlope'
> {
  const period = LOOP_S.flyby;
  const phase = (t % period) / period; // 0..1
  // Range: 250 → 30 (CPA at phase 0.5) → 250
  const rangeM = 30 + (250 - 30) * Math.abs(2 * phase - 1);
  // Closing rate: derivative of range w.r.t. time, signed
  const rangePrev = 30 + (250 - 30) * Math.abs(2 * (phase - 0.01) - 1);
  const closingMps = (rangeM - rangePrev) / (period * 0.01);
  // Bearing rotates ~120° as the target passes
  const bearingDeg = 60 + 120 * phase;
  const rssiDb = rssiFromRange(rangeM, jitter(t * 7.3, 0.4));
  const confidence = 0.7 + 0.2 * (1 - Math.abs(2 * phase - 1));
  return {
    timeS: t,
    rangeM,
    bearingDeg,
    closingMps,
    rssiDb,
    confidence,
  };
}

function hoverFrame(t: number) {
  const rangeM = 120 + jitter(t * 0.7, 1.2);
  const bearingDeg = 80 + 8 * Math.sin(t / 6);
  const rssiDb = rssiFromRange(rangeM, jitter(t * 11.1, 0.3));
  return {
    timeS: t,
    rangeM,
    bearingDeg,
    closingMps: 0,
    rssiDb,
    confidence: 0.6 + jitter(t * 3.3, 0.05),
  };
}

function loiterOrbitFrame(t: number) {
  const period = LOOP_S.loiter_orbit;
  const phase = (t % period) / period;
  const rangeM = 110 + 30 * Math.sin(2 * Math.PI * phase);
  const rangePrev = 110 + 30 * Math.sin(2 * Math.PI * (phase - 0.01));
  const closingMps = (rangeM - rangePrev) / (period * 0.01);
  const bearingDeg = 360 * phase;
  const rssiDb = rssiFromRange(rangeM, jitter(t * 5.5, 0.5));
  return {
    timeS: t,
    rangeM,
    bearingDeg,
    closingMps,
    rssiDb,
    confidence: 0.62,
  };
}

function burstyCommsFrame(t: number) {
  const period = LOOP_S.bursty_comms;
  const phase = (t % period) / period;
  // Range: 220 → 60 over the loop, linear close
  const rangeM = 220 - (220 - 60) * phase;
  const closingMps = -(220 - 60) / period;
  const bearingDeg = 110 + 4 * Math.sin(t / 4);
  // Burst gating: 2.4s ON, 1.6s OFF
  const cycleS = 4.0;
  const onS = 2.4;
  const emitting = t % cycleS < onS;
  const rssiDb = rssiFromRange(rangeM, jitter(t * 9.1, 0.6));
  return {
    timeS: t,
    rangeM,
    bearingDeg,
    closingMps,
    rssiDb,
    confidence: emitting ? 0.55 + 0.2 * phase : 0.3,
    emitting,
  };
}

function evasiveZigzagFrame(t: number) {
  const period = LOOP_S.evasive_zigzag;
  const phase = (t % period) / period;
  const rangeM = 250 - (250 - 40) * phase + jitter(t * 4.1, 6);
  const closingMps = -(250 - 40) / period;
  const bearingDeg = 200 + 18 * Math.sin(t * 1.3) + jitter(t * 2.1, 4);
  const rssiDb = rssiFromRange(rangeM, jitter(t * 17.7, 0.9));
  return {
    timeS: t,
    rangeM,
    bearingDeg,
    closingMps,
    rssiDb,
    confidence: 0.45 + 0.15 * Math.sin(t / 3),
  };
}

/**
 * Produce one mock frame for the given scenario at simulated time `t`.
 * `state` is mutated to track the previous RSSI for slope calculation —
 * pass the same state object across consecutive ticks.
 *
 * Throws for `direct_approach`: that scenario is not mocked, the live
 * backend stream is used instead.
 */
export function generateMockFrame(
  scenario: ScenarioId,
  t: number,
  dt: number,
  state: GeneratorState,
): RadarPayload {
  if (scenario === 'direct_approach') {
    throw new Error(
      'direct_approach is live-backed; do not call generateMockFrame for it',
    );
  }

  let raw;
  let emitting = true;
  switch (scenario) {
    case 'flyby':
      raw = flybyFrame(t);
      break;
    case 'hover':
      raw = hoverFrame(t);
      break;
    case 'loiter_orbit':
      raw = loiterOrbitFrame(t);
      break;
    case 'bursty_comms': {
      const f = burstyCommsFrame(t);
      emitting = f.emitting;
      raw = f;
      break;
    }
    case 'evasive_zigzag':
      raw = evasiveZigzagFrame(t);
      break;
  }

  const prev = state.prevRssi;
  const rssiSlope = prev !== null ? (raw.rssiDb - prev) / dt : 0;
  state.prevRssi = raw.rssiDb;

  return buildPayload({
    ...raw,
    scenario,
    rssiSlope,
    emitting,
  });
}

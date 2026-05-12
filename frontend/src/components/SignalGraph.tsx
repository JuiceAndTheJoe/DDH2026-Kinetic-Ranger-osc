import { useEffect, useState } from 'react';
import type { TargetState } from '../lib/types';

/**
 * TODO: Replace SVG sparkline with Recharts <LineChart> or Chart.js for production.
 * The history buffer pattern below is the right hook — just swap the render.
 */

interface Props {
  targets: TargetState[];
}

interface HistoryPoint {
  t: number;  // epoch seconds
  rssi: number;
}

const MAX_HISTORY = 60;
const RSSI_MIN = -110;
const RSSI_MAX = -20;

function toSvgCoords(points: HistoryPoint[]): string {
  if (points.length < 2) return '';
  const now = points[points.length - 1].t;
  const span = 60; // seconds shown
  return points
    .map((p) => {
      const x = (((p.t - now) / span + 1) * 200).toFixed(1);
      const y = (((RSSI_MAX - p.rssi) / (RSSI_MAX - RSSI_MIN)) * 80 + 10).toFixed(1);
      return `${x},${y}`;
    })
    .join(' ');
}

export default function SignalGraph({ targets }: Props) {
  const [history, setHistory] = useState<HistoryPoint[]>([]);

  useEffect(() => {
    if (targets.length === 0) return;
    const rssi = targets[0].rssi_db;
    setHistory((prev) => {
      const next = [...prev, { t: Date.now() / 1000, rssi }];
      return next.slice(-MAX_HISTORY);
    });
  }, [targets]);

  const points = toSvgCoords(history);

  return (
    <div className="panel signal-graph">
      <div className="panel-header">RSSI HISTORY</div>
      <svg className="graph-svg" viewBox="0 0 200 100" xmlns="http://www.w3.org/2000/svg">
        {/* Grid lines */}
        {[-30, -50, -70, -90].map((db) => {
          const y = (((RSSI_MAX - db) / (RSSI_MAX - RSSI_MIN)) * 80 + 10).toFixed(1);
          return (
            <g key={db}>
              <line x1="0" y1={y} x2="200" y2={y} stroke="#1e3a5f" strokeWidth="0.5" />
              <text x="2" y={parseFloat(y) - 1} fontSize="5" fill="#4a6a8a">
                {db}
              </text>
            </g>
          );
        })}
        {/* RSSI polyline */}
        {points && (
          <polyline
            points={points}
            fill="none"
            stroke="#38bdf8"
            strokeWidth="1.5"
          />
        )}
      </svg>
    </div>
  );
}

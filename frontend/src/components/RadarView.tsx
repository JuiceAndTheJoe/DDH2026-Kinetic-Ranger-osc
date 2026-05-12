import { useRef } from 'react';
import type { TargetState } from '../lib/types';

/**
 * TODO (PixiJS): Import Application and Graphics from 'pixi.js'.
 * Replace the SVG placeholder with:
 *   const app = new Application();
 *   await app.init({ canvas: canvasRef.current, resizeTo: canvasRef.current.parentElement });
 * Use Graphics to draw sweep rings and a rotating sweep line each tick.
 * On every `targets` prop change, update blip sprite positions:
 *   x = cx + radial_ttc_norm * radius * Math.sin(bearing_deg * DEG2RAD)
 *   y = cy - radial_ttc_norm * radius * Math.cos(bearing_deg * DEG2RAD)
 * Vite handles PixiJS v8 ESM natively — no CRACO / webpack config needed.
 * Return app.destroy(true) from the useEffect cleanup.
 */

interface Props {
  targets: TargetState[];
}

const RINGS = [0.25, 0.5, 0.75, 1.0];
const DEG2RAD = Math.PI / 180;

export default function RadarView({ targets }: Props) {
  // canvasRef is the mount point for the future PixiJS Application.
  const canvasRef = useRef<HTMLDivElement>(null);

  return (
    <div className="panel radar-view" ref={canvasRef}>
      <div className="panel-header">RADAR VIEW — PixiJS pending</div>

      <div className="radar-scope">
        {/* SVG placeholder: concentric range rings + crosshairs */}
        <svg className="radar-rings" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
          {RINGS.map((r) => (
            <circle
              key={r}
              cx="100"
              cy="100"
              r={r * 90}
              fill="none"
              stroke="#1e3a5f"
              strokeWidth="1"
            />
          ))}
          <line x1="100" y1="10" x2="100" y2="190" stroke="#1e3a5f" strokeWidth="0.5" />
          <line x1="10" y1="100" x2="190" y2="100" stroke="#1e3a5f" strokeWidth="0.5" />
        </svg>

        {/* CSS-positioned target blips using polar → cartesian */}
        {targets.map((t) => {
          const rad = t.display.bearing_deg * DEG2RAD;
          const r = t.display.radial_ttc_norm * 45; // percent of scope radius
          const x = 50 + r * Math.sin(rad);          // % from left
          const y = 50 - r * Math.cos(rad);          // % from top
          return (
            <div
              key={t.id}
              className={`radar-blip radar-blip--${t.threat_level.toLowerCase()}`}
              style={{ left: `${x}%`, top: `${y}%` }}
              title={`${t.id} | ${t.threat_level} | TTC ${t.estimated_ttc_s < 0 ? '—' : t.estimated_ttc_s.toFixed(1) + 's'}`}
            />
          );
        })}

        {/* Sensor origin marker */}
        <div className="radar-origin" />
      </div>
    </div>
  );
}

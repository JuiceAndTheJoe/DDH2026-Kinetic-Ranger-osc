import { useEffect, useRef, useState } from 'react';
import { Application, Graphics } from 'pixi.js';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import type { TargetState } from '../lib/types';

interface Props {
  targets: TargetState[];
}

/**
 * Default radar range in meters at startup. The four concentric rings
 * represent 25%, 50%, 75%, 100% of the current range, and the map auto-zooms
 * so its visible radius matches the outer ring — distances on the map and
 * on the radar are 1:1.
 *
 * The range is operator-controlled via a slider; the constant below is just
 * the initial value.
 */
const DEFAULT_RANGE_M = 2000;
const MIN_RANGE_M = 100;
const MAX_RANGE_M = 5000;
const RANGE_STEP_M = 100;
const RING_FRACTIONS = [0.25, 0.5, 0.75, 1.0];
const DEG2RAD = Math.PI / 180;
// Abstract dark vector style — roads, parks, water, country boundaries, no
// photographic buildings. Swap candidates if you want a different look:
//   'mapbox://styles/mapbox/light-v11'           — abstract light
//   'mapbox://styles/mapbox/navigation-night-v1' — even sparser, navigation-focused
//   'mapbox://styles/mapbox/satellite-streets-v12' — original photographic
const MAP_STYLE = 'mapbox://styles/mapbox/dark-v11';
const FALLBACK_POSITION = { lat: 59.3293, lng: 18.0686 };

// PixiJS draws the rotating sweep line only — the static rings, distance
// labels, and cardinal letters live in SVG below so they can react to the
// operator-controlled range and heading without recomputing canvas geometry.
const SWEEP_PERIOD_MS = 6000;
const SWEEP_COLOR = 0x50ffd7;

function drawSweep(app: Application, sweep: Graphics): void {
  const cx = app.screen.width / 2;
  const cy = app.screen.height / 2;
  const maxR = (Math.min(app.screen.width, app.screen.height) / 2) * 0.9;

  sweep.x = cx;
  sweep.y = cy;
  sweep.clear();
  sweep.moveTo(0, 0).lineTo(0, -maxR).stroke({ color: SWEEP_COLOR, width: 1.5, alpha: 0.9 });
  for (let i = 1; i <= 8; i++) {
    const a = -i * 5 * DEG2RAD;
    sweep
      .moveTo(0, 0)
      .lineTo(Math.sin(a) * maxR, -Math.cos(a) * maxR)
      .stroke({ color: SWEEP_COLOR, width: 1, alpha: Math.max(0, 0.15 - i * 0.015) });
  }
}

type MapStatus = 'loading' | 'ready' | 'missing-token' | 'error';
type LocationStatus = 'pending' | 'acquired' | 'fallback';

function metersToLatLngDelta(lat: number, meters: number) {
  const dLat = meters / 111320;
  const dLng = meters / (111320 * Math.cos(lat * DEG2RAD));
  return { dLat, dLng };
}

function formatRangeMeters(m: number): string {
  if (m >= 1000) {
    const km = m / 1000;
    return `${km.toFixed(km % 1 === 0 ? 0 : 1)} km`;
  }
  return `${Math.round(m)} m`;
}

export default function RadarView({ targets }: Props) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const scopeRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pixiRef = useRef<Application | null>(null);

  const [mapStatus, setMapStatus] = useState<MapStatus>('loading');
  const [locationStatus, setLocationStatus] = useState<LocationStatus>('pending');
  const [position, setPosition] = useState(FALLBACK_POSITION);
  const [maxRangeM, setMaxRangeM] = useState(DEFAULT_RANGE_M);
  // Heading-up: the compass direction (deg, 0–359) that the operator is facing.
  // When non-zero, the map, rings, cardinal letters and blip placement all
  // rotate so that the user's facing direction is at the top of the display.
  const [heading, setHeading] = useState(0);

  // Draft strings for the editable inputs. The canonical state lives in
  // `maxRangeM` / `heading`; drafts mirror it but can hold intermediate
  // typing (empty, partial numbers) without clamping until commit.
  const [rangeDraft, setRangeDraft] = useState(String(DEFAULT_RANGE_M));
  const [headingDraft, setHeadingDraft] = useState('0');
  useEffect(() => {
    setRangeDraft(String(maxRangeM));
  }, [maxRangeM]);
  useEffect(() => {
    setHeadingDraft(String(heading));
  }, [heading]);

  function commitRange(raw: string) {
    const num = Number(raw);
    if (!Number.isFinite(num)) {
      setRangeDraft(String(maxRangeM));
      return;
    }
    const clamped = Math.max(MIN_RANGE_M, Math.min(MAX_RANGE_M, Math.round(num)));
    setMaxRangeM(clamped);
  }

  function commitHeading(raw: string) {
    const num = Number(raw);
    if (!Number.isFinite(num)) {
      setHeadingDraft(String(heading));
      return;
    }
    const wrapped = ((Math.round(num) % 360) + 360) % 360;
    setHeading(wrapped);
  }

  // Ref mirrors so the once-on-mount map-load handler reads the latest values
  // without forcing the whole map to recreate when controls change.
  const rangeRef = useRef(maxRangeM);
  rangeRef.current = maxRangeM;
  const positionRef = useRef(position);
  positionRef.current = position;
  const headingRef = useRef(heading);
  headingRef.current = heading;

  // Geolocation
  useEffect(() => {
    let cancelled = false;
    if (!navigator.geolocation) {
      setLocationStatus('fallback');
      return undefined;
    }

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        if (cancelled) return;
        setPosition({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setLocationStatus('acquired');
      },
      () => {
        if (cancelled) return;
        setLocationStatus('fallback');
      },
      {
        enableHighAccuracy: false,
        timeout: 8000,
        maximumAge: 60000,
      },
    );

    return () => {
      cancelled = true;
    };
  }, []);

  // Mapbox
  useEffect(() => {
    const token = import.meta.env.VITE_MAPBOX_TOKEN;
    if (!mapContainerRef.current) return undefined;

    if (!token) {
      setMapStatus('missing-token');
      return undefined;
    }

    mapboxgl.accessToken = token;
    setMapStatus('loading');

    let map: mapboxgl.Map | null = null;
    try {
      map = new mapboxgl.Map({
        container: mapContainerRef.current,
        style: MAP_STYLE,
        center: [position.lng, position.lat],
        zoom: 13,
        bearing: 0,
        pitch: 0,
        interactive: false,
      });
    } catch (err) {
      setMapStatus('error');
      return undefined;
    }

    mapRef.current = map;

    const fitToRange = () => {
      const m = mapRef.current;
      if (!m) return;
      const pos = positionRef.current;
      const range = rangeRef.current;
      const bearing = headingRef.current;
      const { dLat, dLng } = metersToLatLngDelta(pos.lat, range);
      m.fitBounds(
        [
          [pos.lng - dLng, pos.lat - dLat],
          [pos.lng + dLng, pos.lat + dLat],
        ],
        { padding: 0, animate: false, duration: 0, bearing },
      );
    };

    const handleLoad = () => {
      map?.resize();
      fitToRange();
      setMapStatus('ready');
    };
    const handleError = () => setMapStatus('error');
    map.on('load', handleLoad);
    map.on('error', handleError);

    const resizeObserver = new ResizeObserver(() => {
      map?.resize();
      fitToRange();
    });
    resizeObserver.observe(mapContainerRef.current);

    return () => {
      map.off('load', handleLoad);
      map.off('error', handleError);
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Refit whenever range, position, or heading changes (post-mount).
  useEffect(() => {
    const m = mapRef.current;
    if (!m || mapStatus !== 'ready') return;
    m.setCenter([position.lng, position.lat]);
    const { dLat, dLng } = metersToLatLngDelta(position.lat, maxRangeM);
    m.fitBounds(
      [
        [position.lng - dLng, position.lat - dLat],
        [position.lng + dLng, position.lat + dLat],
      ],
      { padding: 0, animate: true, duration: 250, bearing: heading },
    );
  }, [maxRangeM, position, heading, mapStatus]);

  // PixiJS sweep — animated rotating line + trailing fade. Painted on its own
  // canvas behind the SVG rings.
  useEffect(() => {
    const canvas = canvasRef.current;
    const scope = scopeRef.current;
    if (!canvas || !scope) return;

    const app = new Application();
    let cancelled = false;

    (async () => {
      await app.init({
        canvas,
        resizeTo: scope,
        backgroundAlpha: 0,
        antialias: true,
        autoDensity: true,
        resolution: window.devicePixelRatio ?? 1,
      });

      if (cancelled) {
        app.destroy(true);
        return;
      }

      const sweep = new Graphics();
      app.stage.addChild(sweep);
      pixiRef.current = app;

      const redraw = () => drawSweep(app, sweep);
      redraw();
      app.renderer.on('resize', redraw);

      app.ticker.add((ticker) => {
        sweep.rotation += ((2 * Math.PI) / SWEEP_PERIOD_MS) * ticker.deltaMS;
      });
    })();

    return () => {
      cancelled = true;
      pixiRef.current?.destroy(true);
      pixiRef.current = null;
    };
  }, []);

  const mapStatusLabel =
    mapStatus === 'missing-token'
      ? 'Mapbox token missing'
      : mapStatus === 'error'
        ? 'Mapbox error'
        : mapStatus === 'ready'
          ? 'Mapbox ready'
          : 'Mapbox loading';

  const locationStatusLabel =
    locationStatus === 'acquired'
      ? 'Location acquired'
      : locationStatus === 'fallback'
        ? 'Location unavailable, using fallback'
        : 'Location pending';

  return (
    <div className="panel radar-view">
      <div className="panel-header">
        <span>RADAR VIEW</span>
        <div className="radar-controls">
          <div className="radar-range-control">
            <label htmlFor="radar-range-slider" className="radar-range-label">
              RANGE
            </label>
            <input
              id="radar-range-slider"
              type="range"
              min={MIN_RANGE_M}
              max={MAX_RANGE_M}
              step={RANGE_STEP_M}
              value={maxRangeM}
              onChange={(e) => setMaxRangeM(Number(e.target.value))}
              className="radar-range-slider"
              aria-label="Radar max range slider"
            />
            <input
              type="number"
              min={MIN_RANGE_M}
              max={MAX_RANGE_M}
              step={RANGE_STEP_M}
              value={rangeDraft}
              onChange={(e) => setRangeDraft(e.target.value)}
              onBlur={(e) => commitRange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  commitRange(e.currentTarget.value);
                  e.currentTarget.blur();
                }
              }}
              className="radar-control-number"
              aria-label="Radar max range (meters)"
            />
            <span className="radar-control-unit">m</span>
          </div>
          <div className="radar-range-control">
            <label htmlFor="radar-heading-slider" className="radar-range-label">
              UP
            </label>
            <input
              id="radar-heading-slider"
              type="range"
              min={0}
              max={359}
              step={1}
              value={heading}
              onChange={(e) => setHeading(Number(e.target.value))}
              className="radar-range-slider"
              aria-label="Direction facing slider (compass degrees)"
            />
            <input
              type="number"
              min={0}
              max={359}
              step={1}
              value={headingDraft}
              onChange={(e) => setHeadingDraft(e.target.value)}
              onBlur={(e) => commitHeading(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  commitHeading(e.currentTarget.value);
                  e.currentTarget.blur();
                }
              }}
              className="radar-control-number"
              aria-label="Direction facing (compass degrees)"
            />
            <span className="radar-control-unit">°</span>
            <button
              type="button"
              className="radar-heading-reset"
              onClick={() => setHeading(0)}
              title="Reset to north-up"
              aria-label="Reset heading to north"
            >
              ↺ N
            </button>
          </div>
        </div>
      </div>

      <div className="radar-scope" ref={scopeRef}>
        <div className="radar-map">
          <div className="radar-map__canvas" ref={mapContainerRef} />
        </div>

        <div className="radar-overlay">
          <canvas
            ref={canvasRef}
            className="radar-sweep-canvas"
          />

          <svg
            className="radar-rings"
            viewBox="0 0 200 200"
            xmlns="http://www.w3.org/2000/svg"
            style={{ transform: `rotate(${-heading}deg)` }}
          >
            {RING_FRACTIONS.map((f) => (
              <g key={f}>
                <circle
                  cx="100"
                  cy="100"
                  r={f * 90}
                  fill="none"
                  stroke="#4f8fd1"
                  strokeWidth="0.4"
                />
                <text
                  x={100 + f * 90 + 4}
                  y={101}
                  fill="#aac6ee"
                  fontSize="5"
                  fontFamily="JetBrains Mono, monospace"
                  letterSpacing="0.5"
                >
                  {formatRangeMeters(f * maxRangeM)}
                </text>
              </g>
            ))}
            <line x1="100" y1="10" x2="100" y2="190" stroke="#4f8fd1" strokeWidth="0.3" />
            <line x1="10" y1="100" x2="190" y2="100" stroke="#4f8fd1" strokeWidth="0.3" />

            <text x="100" y="8" fill="#aac6ee" fontSize="5.5" fontFamily="JetBrains Mono, monospace" textAnchor="middle" letterSpacing="0.6">N</text>
            <text x="100" y="196" fill="#aac6ee" fontSize="5.5" fontFamily="JetBrains Mono, monospace" textAnchor="middle" letterSpacing="0.6">S</text>
            <text x="194" y="102" fill="#aac6ee" fontSize="5.5" fontFamily="JetBrains Mono, monospace" textAnchor="end" letterSpacing="0.6">E</text>
            <text x="6" y="102" fill="#aac6ee" fontSize="5.5" fontFamily="JetBrains Mono, monospace" textAnchor="start" letterSpacing="0.6">W</text>
          </svg>

          {targets.map((t) => {
            // The blip's bearing is in compass degrees (clockwise from north).
            // Subtract the heading so that the operator's facing direction sits
            // at the top of the screen.
            const screenAngleDeg = t.display.bearing_deg - heading;
            const rad = screenAngleDeg * DEG2RAD;
            const radialNorm = Math.min(1, t.range_m / maxRangeM);
            const offRange = t.range_m > maxRangeM;
            const r = radialNorm * 45;
            const x = 50 + r * Math.sin(rad);
            const y = 50 - r * Math.cos(rad);
            const bearingLabel = `${t.display.bearing_deg.toFixed(0)}°`;
            return (
              <div
                key={t.id}
                className="radar-blip-wrapper"
                style={{ left: `${x}%`, top: `${y}%` }}
                title={`${t.id} | ${t.threat_level} | range ${formatRangeMeters(t.range_m)} | bearing ${bearingLabel} | TTC ${t.estimated_ttc_s < 0 ? '--' : t.estimated_ttc_s.toFixed(1) + 's'}`}
              >
                <span
                  className={`radar-blip radar-blip--${t.threat_level.toLowerCase()}${offRange ? ' radar-blip--off-range' : ''}`}
                />
                <span className="radar-blip__label">
                  {formatRangeMeters(t.range_m)} · {bearingLabel}
                </span>
              </div>
            );
          })}

          <div className="radar-origin">
            <span className="radar-origin__label">RX</span>
          </div>
        </div>

        {(mapStatus !== 'ready' || locationStatus !== 'acquired') && (
          <div className="radar-status">
            {mapStatus !== 'ready' && <span>{mapStatusLabel}</span>}
            {mapStatus !== 'ready' && locationStatus !== 'acquired' && (
              <span className="radar-status__sep">|</span>
            )}
            {locationStatus !== 'acquired' && <span>{locationStatusLabel}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

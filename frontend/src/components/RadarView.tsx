import { useEffect, useMemo, useRef, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import type { TargetState } from '../lib/types';

/**
 * Per-bearing signal-strength ring drawn around the radar perimeter.
 *
 * Each of the SPECTRUM_BINS angular bins gets a magnitude in [0, 1] that
 * sums Gaussian contributions from every active target's bearing on top of
 * a flat noise floor. The output drives the radial bars rendered around the
 * outer ring of the SVG — peaks bloom amber wherever a target's bearing
 * sits, baseline bins stay cool blue.
 *
 * Today the per-target amplitude is derived from RSSI as a stand-in. When
 * coherent two-channel AOA + per-azimuth FFT lands, replace the body of
 * this function with the real per-bin power readout — the rendering side
 * stays identical.
 */
const SPECTRUM_BINS = 96;
const SPECTRUM_NOISE_FLOOR = 0.06;
const SPECTRUM_PEAK_SIGMA_DEG = 14;

function computeSpectrum(targets: TargetState[], bins: number): number[] {
  const spectrum = new Array<number>(bins).fill(SPECTRUM_NOISE_FLOOR);
  const binWidth = 360 / bins;
  const sigmaBins = SPECTRUM_PEAK_SIGMA_DEG / binWidth;
  const twoSigmaSq = 2 * sigmaBins * sigmaBins;
  for (const t of targets) {
    const amplitude = Math.min(1, Math.max(0.35, (t.rssi_db + 90) / 30));
    for (let i = 0; i < bins; i++) {
      const binCenter = i * binWidth;
      let diffDeg = Math.abs(binCenter - t.display.bearing_deg);
      if (diffDeg > 180) diffDeg = 360 - diffDeg;
      const diffBins = diffDeg / binWidth;
      const contribution = amplitude * Math.exp(-(diffBins * diffBins) / twoSigmaSq);
      spectrum[i] = Math.min(1, spectrum[i] + contribution);
    }
  }
  return spectrum;
}

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
    return `${km.toFixed(km % 1 === 0 ? 0 : 1)}km`;
  }
  return `${Math.round(m)}m`;
}

export default function RadarView({ targets }: Props) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);

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

  // Per-bearing signal strength — recomputed when the target list changes.
  const spectrum = useMemo(() => computeSpectrum(targets, SPECTRUM_BINS), [targets]);

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
      <div className="radar-scope">
        <div className="radar-map">
          <div className="radar-map__canvas" ref={mapContainerRef} />
        </div>

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

        <div className="radar-overlay">
          <div className="radar-pulse" aria-hidden="true">
            <span />
            <span />
          </div>

          <svg
            className="radar-rings"
            viewBox="0 0 200 200"
            xmlns="http://www.w3.org/2000/svg"
            style={{ transform: `rotate(${-heading}deg)` }}
          >
            {RING_FRACTIONS.map((f) => (
              <circle
                key={`ring-${f}`}
                cx="100"
                cy="100"
                r={f * 90}
                fill="none"
                stroke="#4f8fd1"
                strokeWidth="0.4"
              />
            ))}
            <line x1="100" y1="10" x2="100" y2="190" stroke="#4f8fd1" strokeWidth="0.3" />
            <line x1="10" y1="100" x2="190" y2="100" stroke="#4f8fd1" strokeWidth="0.3" />

            {/* Distance labels — rendered after the rings + crosshairs so the
                halo'd text always sits in front of every blue line. */}
            {RING_FRACTIONS.map((f) => (
              <text
                key={`label-${f}`}
                x={100 + f * 90}
                y={101.2}
                fill="#aac6ee"
                stroke="#0a111d"
                strokeWidth="0.9"
                paintOrder="stroke"
                fontSize="3.6"
                fontFamily="JetBrains Mono, monospace"
                letterSpacing="0.3"
                textAnchor="middle"
              >
                {formatRangeMeters(f * maxRangeM)}
              </text>
            ))}

            {/* Spectrum ring — per-bearing signal strength as radial bars. */}
            {spectrum.map((mag, i) => {
              const theta = (i / spectrum.length) * 2 * Math.PI;
              const r0 = 92;
              const r1 = r0 + mag * 7;
              const sin = Math.sin(theta);
              const cos = Math.cos(theta);
              const x1 = 100 + sin * r0;
              const y1 = 100 - cos * r0;
              const x2 = 100 + sin * r1;
              const y2 = 100 - cos * r1;
              const stroke =
                mag > 0.55 ? '#ffc266' : mag > 0.3 ? '#9ad4ff' : '#3f6791';
              return (
                <line
                  key={i}
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={stroke}
                  strokeWidth={0.9}
                  strokeLinecap="round"
                  opacity={0.35 + mag * 0.55}
                />
              );
            })}

            <text x="100" y="4" fill="#aac6ee" stroke="#0a111d" strokeWidth="0.9" paintOrder="stroke" fontSize="4.5" fontFamily="JetBrains Mono, monospace" textAnchor="middle" letterSpacing="0.6">N</text>
            <text x="100" y="199" fill="#aac6ee" stroke="#0a111d" strokeWidth="0.9" paintOrder="stroke" fontSize="4.5" fontFamily="JetBrains Mono, monospace" textAnchor="middle" letterSpacing="0.6">S</text>
            <text x="199" y="103" fill="#aac6ee" stroke="#0a111d" strokeWidth="0.9" paintOrder="stroke" fontSize="4.5" fontFamily="JetBrains Mono, monospace" textAnchor="end" letterSpacing="0.6">E</text>
            <text x="1" y="103" fill="#aac6ee" stroke="#0a111d" strokeWidth="0.9" paintOrder="stroke" fontSize="4.5" fontFamily="JetBrains Mono, monospace" textAnchor="start" letterSpacing="0.6">W</text>
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

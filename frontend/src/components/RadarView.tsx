import { useEffect, useRef, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
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
const MAP_STYLE = 'mapbox://styles/mapbox/satellite-streets-v12';
const FALLBACK_POSITION = { lat: 59.3293, lng: 18.0686 };

type MapStatus = 'loading' | 'ready' | 'missing-token' | 'error';
type LocationStatus = 'pending' | 'acquired' | 'fallback';

export default function RadarView({ targets }: Props) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const [mapStatus, setMapStatus] = useState<MapStatus>('loading');
  const [locationStatus, setLocationStatus] = useState<LocationStatus>('pending');
  const [position, setPosition] = useState(FALLBACK_POSITION);

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
        zoom: 12,
        bearing: 0,
        pitch: 0,
        interactive: false,
      });
    } catch (err) {
      setMapStatus('error');
      return undefined;
    }

    mapRef.current = map;
    const handleLoad = () => {
      map?.resize();
      setMapStatus('ready');
    };
    const handleError = () => setMapStatus('error');
    map.on('load', handleLoad);
    map.on('error', handleError);

    const resizeObserver = new ResizeObserver(() => {
      map?.resize();
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

  useEffect(() => {
    if (!mapRef.current) return;
    mapRef.current.setCenter([position.lng, position.lat]);
  }, [position]);

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
      <div className="panel-header">RADAR VIEW — PixiJS pending</div>

      <div className="radar-scope">
        <div className="radar-map">
          <div className="radar-map__canvas" ref={mapContainerRef} />
        </div>
        <div className="radar-map__shade" />

        <div className="radar-overlay">
          <svg className="radar-rings" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
            {RINGS.map((r) => (
              <circle
                key={r}
                cx="100"
                cy="100"
                r={r * 90}
                fill="none"
                stroke="#4f8fd1"
                strokeWidth="1"
              />
            ))}
            <line x1="100" y1="10" x2="100" y2="190" stroke="#4f8fd1" strokeWidth="0.6" />
            <line x1="10" y1="100" x2="190" y2="100" stroke="#4f8fd1" strokeWidth="0.6" />
          </svg>

          {targets.map((t) => {
            const rad = t.display.bearing_deg * DEG2RAD;
            const r = t.display.radial_ttc_norm * 45;
            const x = 50 + r * Math.sin(rad);
            const y = 50 - r * Math.cos(rad);
            return (
              <div
                key={t.id}
                className={`radar-blip radar-blip--${t.threat_level.toLowerCase()}`}
                style={{ left: `${x}%`, top: `${y}%` }}
                title={`${t.id} | ${t.threat_level} | TTC ${t.estimated_ttc_s < 0 ? '--' : t.estimated_ttc_s.toFixed(1) + 's'}`}
              />
            );
          })}

          <div className="radar-origin">
            <span className="radar-origin__label">RX</span>
          </div>
        </div>

        <div className="radar-status">
          <span>{mapStatusLabel}</span>
          <span className="radar-status__sep">|</span>
          <span>{locationStatusLabel}</span>
        </div>
      </div>
    </div>
  );
}

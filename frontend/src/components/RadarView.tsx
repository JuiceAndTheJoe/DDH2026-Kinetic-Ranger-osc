import { useEffect, useRef, useState } from 'react';
import { Application, Graphics, Container } from 'pixi.js';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import type { TargetState } from '../lib/types';

interface Props {
  targets: TargetState[];
}

const RINGS_RATIOS = [0.25, 0.5, 0.75, 1.0];
const DEG2RAD = Math.PI / 180;
const MAP_STYLE_WITH_LABELS = 'mapbox://styles/mapbox/satellite-streets-v12';
const MAP_STYLE_NO_LABELS = 'mapbox://styles/mapbox/satellite-v9';
const SHOW_MAP_LABELS = String(import.meta.env.VITE_MAP_LABELS).toLowerCase() === 'true';
const MAP_STYLE = SHOW_MAP_LABELS ? MAP_STYLE_WITH_LABELS : MAP_STYLE_NO_LABELS;
const FALLBACK_POSITION = { lat: 59.3293, lng: 18.0686 };

const SWEEP_PERIOD_MS = 6000;
const RING_COLOR = 0x4f8fd1;
const SWEEP_COLOR = 0x50ffd7;
const BLIP_COLORS: Record<string, number> = {
  CRITICAL: 0xff5252,
  HIGH: 0xfed766,
  LOW: 0x5ac4ff,
  NONE: 0x8ca5c5,
};

function drawScene(app: Application, rings: Graphics, sweep: Graphics): void {
  const cx = app.screen.width / 2;
  const cy = app.screen.height / 2;
  const maxR = (Math.min(app.screen.width, app.screen.height) / 2) * 0.9;

  rings.clear();
  for (const ratio of RINGS_RATIOS) {
    rings.circle(cx, cy, maxR * ratio).stroke({ color: RING_COLOR, width: 1, alpha: 0.78 });
  }
  rings.moveTo(cx, cy - maxR).lineTo(cx, cy + maxR).stroke({ color: RING_COLOR, width: 0.6, alpha: 0.6 });
  rings.moveTo(cx - maxR, cy).lineTo(cx + maxR, cy).stroke({ color: RING_COLOR, width: 0.6, alpha: 0.6 });

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

function drawBlips(app: Application, container: Container, targets: TargetState[]): void {
  const removed = container.removeChildren();
  removed.forEach((c) => c.destroy());

  const cx = app.screen.width / 2;
  const cy = app.screen.height / 2;
  const maxR = (Math.min(app.screen.width, app.screen.height) / 2) * 0.9;

  for (const t of targets) {
    const rad = t.display.bearing_deg * DEG2RAD;
    const r = t.display.radial_ttc_norm * maxR;
    const color = BLIP_COLORS[t.threat_level] ?? BLIP_COLORS.NONE;

    const blip = new Graphics();
    blip.circle(0, 0, 5).fill({ color });
    blip.circle(0, 0, 10).stroke({ color, width: 1, alpha: 0.4 });
    blip.x = cx + r * Math.sin(rad);
    blip.y = cy - r * Math.cos(rad);
    container.addChild(blip);
  }
}

type MapStatus = 'loading' | 'ready' | 'missing-token' | 'error';
type LocationStatus = 'pending' | 'acquired' | 'fallback';

export default function RadarView({ targets }: Props) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const scopeRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pixiRef = useRef<Application | null>(null);
  const blipsRef = useRef<Container | null>(null);
  const targetsRef = useRef<TargetState[]>(targets);
  targetsRef.current = targets;

  const [mapStatus, setMapStatus] = useState<MapStatus>('loading');
  const [locationStatus, setLocationStatus] = useState<LocationStatus>('pending');
  const [position, setPosition] = useState(FALLBACK_POSITION);

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

  // Sync map centre with acquired position
  useEffect(() => {
    if (!mapRef.current) return;
    mapRef.current.setCenter([position.lng, position.lat]);
  }, [position]);

  // PixiJS setup
  useEffect(() => {
    const canvas = canvasRef.current;
    const scope = scopeRef.current;
    if (!canvas || !scope) return;

    const app = new Application();

    (async () => {
      await app.init({
        canvas,
        resizeTo: scope,
        backgroundAlpha: 0,
        antialias: true,
        autoDensity: true,
        resolution: window.devicePixelRatio ?? 1,
      });

      const rings = new Graphics();
      const sweep = new Graphics();
      const blipsContainer = new Container();
      app.stage.addChild(rings, sweep, blipsContainer);
      pixiRef.current = app;
      blipsRef.current = blipsContainer;

      const redraw = () => {
        drawScene(app, rings, sweep);
        drawBlips(app, blipsContainer, targetsRef.current);
      };

      redraw();
      app.renderer.on('resize', redraw);

      app.ticker.add((ticker) => {
        sweep.rotation += ((2 * Math.PI) / SWEEP_PERIOD_MS) * ticker.deltaMS;
      });
    })();

    return () => {
      pixiRef.current?.destroy(true);
      pixiRef.current = null;
      blipsRef.current = null;
    };
  }, []);

  // Redraw blips whenever targets update
  useEffect(() => {
    const app = pixiRef.current;
    const container = blipsRef.current;
    if (!app || !container) return;
    drawBlips(app, container, targets);
  }, [targets]);

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
      <div className="panel-header">RADAR VIEW</div>

      <div className="radar-scope" ref={scopeRef}>
        <div className="radar-map">
          <div className="radar-map__canvas" ref={mapContainerRef} />
        </div>
        <div className="radar-map__shade" />

        <div className="radar-overlay">
          <canvas
            ref={canvasRef}
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', zIndex: 4, pointerEvents: 'none' }}
          />
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

import { useEffect, useRef, useState } from 'react';
import './App.css';
import MetricsPanel from './components/MetricsPanel';
import RadarView from './components/RadarView';
import SignalGraph from './components/SignalGraph';
import SimulationControls from './components/SimulationControls';
import ThreatBanner from './components/ThreatBanner';
import { RadarWebSocket } from './lib/websocket';
import type { ConnectionState, RadarPayload } from './lib/types';

const WS_URL = 'ws://localhost:8000/ws/radar';

export default function App() {
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [payload, setPayload] = useState<RadarPayload | null>(null);
  const wsRef = useRef<RadarWebSocket | null>(null);

  useEffect(() => {
    const ws = new RadarWebSocket(WS_URL, setPayload, setConnectionState);
    wsRef.current = ws;
    ws.connect();
    return () => {
      ws.disconnect();
    };
  }, []);

  return (
    <div className="dashboard">
      <ThreatBanner
        summary={payload?.summary ?? null}
        connectionState={connectionState}
      />

      <div className="dashboard-main">
        <div className="dashboard-left">
          <RadarView targets={payload?.targets ?? []} />
        </div>

        <div className="dashboard-right">
          <MetricsPanel
            targets={payload?.targets ?? []}
            timeS={payload?.time_s ?? 0}
          />
          <SignalGraph targets={payload?.targets ?? []} />
          <SimulationControls />
        </div>
      </div>
    </div>
  );
}

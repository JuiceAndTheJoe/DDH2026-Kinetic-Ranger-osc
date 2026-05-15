# Frontend

This folder contains the Vite + React + TypeScript dashboard for Kinetic Ranger.

## What it does today

- connects to backend WebSocket via env-configurable URL
- shows the threat banner, radar display, metrics, and RSSI history
- renders simulated backend data in real time

## What it does not do yet

- the controls in `SimulationControls.tsx` are still local UI state only
- there are no REST endpoints yet for starting, pausing, resetting, or reconfiguring the simulation

## Install

From this folder:

```text
pnpm install
```

## Run

Start the backend first from the repository root:

```text
python -m uvicorn kinetic_ranger.api.main:app --reload --port 8000
```

Then start the frontend from this folder:

```text
pnpm dev
```

Useful commands:

```text
pnpm lint
pnpm build
pnpm preview
```

## Important implementation notes

- REST base URL is controlled by `VITE_API_BASE_URL` (default `http://localhost:8000`)
- WebSocket URL is controlled by `VITE_WS_URL`, or derived from API base to `/ws/radar`
- TypeScript is configured with `erasableSyntaxOnly`, so avoid TypeScript features that require emitted runtime transforms, such as constructor parameter properties
- the dashboard expects simulation payloads shaped like `frontend/src/lib/types.ts`, which must stay aligned with `src/kinetic_ranger/api/schemas.py`

## Main files

- `src/App.tsx` — top-level layout and WebSocket hookup
- `src/components/RadarView.tsx` — radar-style visualization
- `src/components/MetricsPanel.tsx` — target metrics
- `src/components/SignalGraph.tsx` — RSSI history graph
- `src/components/SimulationControls.tsx` — simulation control scaffold
- `src/lib/types.ts` — frontend wire types
- `src/lib/websocket.ts` — reconnecting WebSocket client

# Kinetic Ranger

Kinetic Ranger is an early-stage passive RF threat-detection prototype with:

- a Python backend package in `src/kinetic_ranger`
- a FastAPI server that exposes a health endpoint and a simulation WebSocket
- a React + TypeScript + Vite frontend in `frontend/`
- simulation-first workflows, with optional live SDR support behind a separate capture layer

Right now, the repository is best thought of as an MVP scaffold that already runs end-to-end in simulation.

## What currently works

### Backend

- `python -m kinetic_ranger simulate` runs the synthetic approach simulation in the terminal
- `python -m kinetic_ranger replay <observations.csv>` replays extracted observations from CSV
- `python -m kinetic_ranger live --iterations 10` reads from an IIO-compatible receiver when the optional hardware dependency is installed
- `python -m uvicorn kinetic_ranger.api.main:app --reload --port 8000` starts a FastAPI app with:
  - `GET /health`
  - `WS /ws/radar`

### Frontend

- `pnpm dev` starts the Vite dashboard
- the UI connects to `ws://localhost:8000/ws/radar`
- the radar view, metrics panel, threat banner, and RSSI history graph render live simulation frames

### Tests

- backend unit tests cover alerting, estimator logic, and feature extraction in `tests/`

## Requirements

- Python 3.11+
- Node.js 20+
- `pnpm` for frontend package management

## Setup

### Python environment

From the repository root, create and activate a virtual environment however you prefer, then install the package:

```text
pip install -e .[dev]
```

Optional extras:

```text
pip install -e .[dev,hardware,viz]
```

Use the `hardware` extra only if you want the live SDR path. The default development flow works without it.

### Frontend dependencies

From `frontend/`:

```text
pnpm install
```

## Running the project

### Terminal simulation

From the repository root:

```text
python -m kinetic_ranger simulate
```

Useful variants:

```text
python -m kinetic_ranger simulate --log-dir logs
python -m kinetic_ranger replay path\to\observations.csv
python -m kinetic_ranger live --iterations 10
```

### Dashboard

Start the backend from the repository root:

```text
python -m uvicorn kinetic_ranger.api.main:app --reload --port 8000
```

Start the frontend from `frontend/`:

```text
pnpm dev
```

Local URLs:

- API health: <http://localhost:8000/health>
- dashboard: usually <http://localhost:5173>
- WebSocket feed: `ws://localhost:8000/ws/radar`

## Configuration

Default runtime values live in `configs/default.toml`.

Key sections:

- `[radio]` — SDR URI, sample rate, tuning, gain
- `[telemetry]` — CSV telemetry replay settings
- `[estimator]` — EKF initial state and noise tuning
- `[alert]` — alert thresholds and hysteresis
- `[simulation]` — synthetic approach timing and noise parameters

If you run commands from an unusual working directory, pass `--config` explicitly.

## Project layout

```text
DDH2026/
├── configs/
│   └── default.toml
├── frontend/
│   ├── package.json
│   └── src/
│       ├── App.tsx
│       ├── components/
│       └── lib/
├── src/
│   └── kinetic_ranger/
│       ├── api/
│       ├── alerting/
│       ├── estimation/
│       ├── logging/
│       ├── radio/
│       ├── telemetry/
│       ├── ui/
│       ├── cli.py
│       ├── config.py
│       └── models.py
└── tests/
```

## Notes about current limitations

- the frontend simulation controls are currently UI-only and are not wired to backend endpoints yet
- the backend WebSocket serves simulated data only
- the live SDR path is optional and assumes an IIO-compatible device workflow
- the frontend currently assumes the backend is available at `localhost:8000`

## Development checks

From the repository root:

```text
pytest
```

From `frontend/`:

```text
pnpm lint
pnpm build
```

## Frontend docs

See `frontend/README.md` for frontend-specific notes.

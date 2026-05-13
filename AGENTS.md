# AGENTS.md

Lightweight guidance for AI coding agents working in this repository.

This project is still early-stage and likely to be restructured. Treat the notes below as **working guidance, not rigid law**: prefer preserving momentum, keeping changes easy to reshape, and avoiding premature abstractions.

## Project snapshot

Kinetic Ranger is a passive RF closure-detection MVP with:

- a Python backend/package in `src/kinetic_ranger`
- a FastAPI + WebSocket API for a live radar-style feed
- a React + TypeScript + Vite frontend in `frontend/`
- simulation-first workflows, with optional live hardware support later

Start by reading:

- root [`README.md`](./README.md)
- frontend [`frontend/README.md`](./frontend/README.md)
- default runtime config [`configs/default.toml`](./configs/default.toml)

## Repo map

### Backend modules

Important areas in `src/kinetic_ranger/`:

- `cli.py` — CLI entrypoints: `simulate`, `replay`, `live`, `export`
- `logging/run_writer.py`, `logging/run_reader.py`, `logging/exporter.py` — run-directory I/O. `RunWriter` is the canonical writer used by every CLI subcommand and by the FastAPI replay path; `RunReader` parses it back; `export_run` produces flat CSVs (observations / alerts / telemetry).
- `api/main.py` — FastAPI app setup and CORS
- `api/websocket.py` / `api/simulation_service.py` — WebSocket streaming path. `SimulationService` is the synthetic source; `ReplayFrameSource` (same file) drives the same pipeline from a recorded run when `KR_REPLAY_SOURCE` is set.
- `radio/capture.py` — simulation and hardware capture interfaces
- `radio/features.py` — IQ-window feature extraction
- `estimation/ekf.py` — tracking / estimation logic
- `alerting/rules.py` — alert evaluation and severity logic
- `config.py` — TOML config loading
- `models.py` / `api/schemas.py` — data and wire-shape definitions

### Frontend modules

Important areas in `frontend/src/`:

- `App.tsx` — app composition and WebSocket hookup
- `components/RadarView.tsx` — main radar visualization
- `components/MetricsPanel.tsx` — target metrics
- `components/SignalGraph.tsx` — signal trends/history
- `components/ThreatBanner.tsx` — top-level status banner
- `components/SimulationControls.tsx` — simulation-facing controls
- `lib/types.ts` — frontend wire types
- `lib/websocket.ts` — WebSocket client lifecycle/reconnect logic

## Preferred workflow

### Keep changes small and reshapeable

Because the repo is still settling:

- prefer small, local changes over big architectural rewrites
- avoid introducing heavy abstractions unless a pattern is clearly repeating
- preserve readable code and clear data flow over cleverness
- if a rename or restructure is needed, keep it surgical and easy to undo

### Respect the simulation-first path

Unless the task is explicitly about hardware:

- prefer simulation, replay, and tests over assumptions about live SDR behavior
- keep hardware-specific logic isolated behind the capture layer
- do not make the live path mandatory for normal development

### Keep backend/frontend contracts aligned

When changing radar payloads or UI data:

- update backend wire models in `src/kinetic_ranger/api/schemas.py`
- update matching frontend types in `frontend/src/lib/types.ts`
- check WebSocket consumers in `frontend/src/App.tsx` and related components

## Useful commands

Run these from the repo root unless noted otherwise.

### Backend commands

- install dev dependencies: `pip install -e .[dev]`
- install optional hardware + viz extras: `pip install -e .[dev,hardware,viz]`
- run tests: `pytest`
- run CLI simulation: `python -m kinetic_ranger simulate`
- run API server: `python -m uvicorn kinetic_ranger.api.main:app --reload --port 8000`

### Frontend commands

Run these in `frontend/`:

- install dependencies: `pnpm install`
- start dev server: `pnpm dev`
- build production bundle: `pnpm build`
- lint: `pnpm lint`

## Practical gotchas

- `configs/default.toml` is the default runtime config; running from unusual working directories may require an explicit `--config`.
- The frontend expects the backend WebSocket at `ws://localhost:8000/ws/radar` unless changed in code.
- CORS in `src/kinetic_ranger/api/main.py` is currently set for the Vite dev server at `http://localhost:5173`.
- The live SDR path depends on optional hardware support (`pyadi-iio` via the `hardware` extra).
- The live path currently assumes Pluto/IIO-compatible workflows; keep hardware assumptions contained and easy to swap.
- Type drift between `api/schemas.py` and `frontend/src/lib/types.ts` is an easy way to break the UI quietly.

## Change guidance for agents

When contributing here:

- prefer updating existing patterns before inventing new ones
- keep comments and docs brief and practical
- add tests when changing estimator, alerting, parsing, or feature-extraction behavior
- avoid broad cleanup unrelated to the task unless it is required to make the change safe
- if the structure changes, update this file lightly rather than trying to make it exhaustive

## When unsure

Use the current code as the source of truth, and treat this file as a fast-start map.
If the repo evolves, favor adapting to the new shape over preserving outdated instructions.

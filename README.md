# Kinetic Ranger

Passive RF closure detection and rough time-to-impact estimation for a single AntSDR E200 receiver.

This repository is scaffolded for the hackathon MVP described in `plan-kineticRangerMvp.prompt.md`:

- host-side processing on Linux
- AntSDR E200 over Ethernet via IIO/libiio-compatible workflows
- signal observables from IQ windows: RSSI, CFO/Doppler proxy, SNR, confidence
- a lightweight estimator for range proxy, closing rate, and time-to-impact
- conservative alerting and replayable experiment logs

## Current status

This is an **initial project scaffold** designed to let you:

1. run simulation and replay flows before hardware is fully integrated,
2. keep AntSDR-specific code behind a small capture interface,
3. validate estimation and alerting logic with unit tests.

The live-radio path is intentionally lightweight and assumes a Pluto-compatible IIO firmware path when using `pyadi-iio`.

## Quick start

### 1. Create a virtual environment

Use any Python 3.11+ environment manager you like.

### 2. Install the package

```text
pip install -e .[dev]
```

Optional extras:

```text
pip install -e .[dev,hardware,viz]
```

### 3. Run the built-in simulation

```text
python -m kinetic_ranger simulate
```

### 4. Run the tests

```text
pytest
```

## Web dashboard (FastAPI + Vite)

Backend (simulation stream + health):

```text
python -m uvicorn kinetic_ranger.api.main:app --reload --port 8000
```

Frontend (Vite + React):

```text
cd frontend
npm install
npm run dev
```

Expected local URLs:

- Backend health: http://localhost:8000/health
- Frontend: Vite dev server URL printed in the terminal
- WebSocket: ws://localhost:8000/ws/radar

## Default config

The default runtime settings live in `configs/default.toml`.

Important values to calibrate once hardware is available:

- `radio.uri`
- `radio.center_frequency_hz`
- `radio.gain_db`
- `estimator.initial_effective_power_db`
- `estimator.path_loss_exponent`
- `alert.tti_threshold_s`

## Suggested workflow

1. start with `simulate` to verify the estimator loop,
2. capture static test IQ from the E200,
3. replay extracted observables against recorded telemetry,
4. calibrate path-loss and alert thresholds,
5. run controlled quadcopter approach tests.

## Repository layout

```text
DDH2026/
├── configs/
│   └── default.toml
├── src/
│   └── kinetic_ranger/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── models.py
│       ├── alerting/
│       │   ├── __init__.py
│       │   └── rules.py
│       ├── estimation/
│       │   ├── __init__.py
│       │   └── ekf.py
│       ├── logging/
│       │   ├── __init__.py
│       │   └── session_logger.py
│       ├── radio/
│       │   ├── __init__.py
│       │   ├── capture.py
│       │   └── features.py
│       ├── telemetry/
│       │   ├── __init__.py
│       │   └── ingest.py
│       └── ui/
│           ├── __init__.py
│           └── dashboard.py
├── tests/
│   ├── test_alerting.py
│   ├── test_estimator.py
│   └── test_features.py
├── plan-kineticRangerMvp.prompt.md
├── pyproject.toml
└── README.md
```

## Hardware notes

- AntSDR E200 docs indicate support for IIO/libiio and UHD workflows over Ethernet.
- For the hackathon MVP, prefer **IIO/libiio first** and keep FPGA changes out of scope.
- Use **fixed gain** for ranging experiments whenever possible; AGC can make RSSI-based estimation much less stable.
- Treat time-to-impact as a **confidence-banded estimate**, not ground truth.

## Next steps

- replace the simulation capture with a tested E200 acquisition path,
- add replay tooling for real telemetry logs,
- collect calibration data for path-loss and alert thresholds,
- optionally add a lightweight dashboard once live testing begins.

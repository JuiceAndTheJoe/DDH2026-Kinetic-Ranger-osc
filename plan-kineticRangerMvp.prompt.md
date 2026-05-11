## Plan: Kinetic Ranger MVP

Build a host-centric passive ranging prototype around the AntSDR E200 that detects a rapidly approaching transmitter and estimates rough time-to-impact using RSSI trend + carrier/frequency offset trend + known sensor motion. This is the best hackathon-risk tradeoff because it avoids requiring calibrated transmitter power, phase-coherent ranging, extra SDRs, or FPGA changes while still giving a defensible demo on a quadcopter.

**Steps**

1. Phase 1 — Environment and radio bring-up. Prepare an Ubuntu 22.04 host laptop connected over Ethernet to the AntSDR E200. Start with the vendor-supported IIO/libiio path for fastest setup; only switch to UHD if a needed feature is missing. Verify network connectivity, tuning, sample capture, gain control, and stable RSSI/CFO extraction from a known test signal.
2. Phase 1 — Project skeleton. Create a small Python project with modules for radio capture, feature extraction, state estimation, alerting, and flight/test logging. Keep the GUI optional so the estimator can run headless during field tests. This can run in parallel with step 1 once the preferred interface is chosen.
3. Phase 2 — Signal observables pipeline. Implement a streaming receiver that tunes to the target band, performs channelization/filtering, and outputs per-window observables: timestamp, center frequency, RSSI, noise floor, AGC/fixed-gain state, CFO or Doppler proxy, confidence/SNR, and optional spectral width. Use fixed gain during ranging experiments so RSSI remains interpretable. Depends on 1.
4. Phase 2 — Motion ingest. Ingest sensor motion from the quadcopter/autopilot telemetry or a synchronized flight log: GPS position, ground speed, heading, altitude, and timestamps. Convert to a consistent local frame and compute ego radial-motion features relative to the estimated threat direction when possible. Depends on 1.
5. Phase 3 — MVP estimator. Implement a lightweight EKF or simpler confidence-scored heuristic filter whose state is at minimum relative range proxy, closing-rate proxy, and transmitter-power bias term. Use RSSI slope plus CFO trend and sensor motion to estimate whether the source is closing rapidly; compute time-to-impact only when the closing-rate estimate is stable and negative. Depends on 3 and 4.
6. Phase 3 — Alert logic. Define conservative thresholds for “unknown radio closing rapidly” using multiple conditions: sustained RSSI increase, negative closing-rate estimate, confidence above threshold, and time-to-impact below a chosen limit. Include hysteresis and cooldown to avoid chatter. Depends on 5.
7. Phase 4 — Field validation harness. Build a logging-and-replay workflow for quadcopter runs so every flight can be replayed offline. Record raw or decimated IQ as needed, observables, telemetry, estimator state, and alerts. Depends on 3, 4, and 5.
8. Phase 4 — Flight test progression. Validate first with a stationary or handheld transmitter at known distances, then with controlled straight-in quad approaches, then with off-axis passes. Use the directional antenna mainly to improve SNR and suppress clutter, not as a full bearing sensor in the MVP. Depends on 7.
9. Phase 5 — Demo packaging. Add a simple dashboard or terminal UI showing current frequency, RSSI trend, closing/not-closing classification, estimated time-to-impact, and recent alert history. This can run in parallel with step 8 after the estimator output is stable.
10. Phase 5 — Stretch goals. If the MVP is stable early, add one of: antenna-pattern-assisted bearing cue, particle filter for non-linear geometry, multi-band classifier, or embedded processing on the E200 ARM. Do not attempt phase-coherent ranging or multi-sensor TDOA for the initial hackathon demo.

**Relevant files**

- `c:\Users\einar\Programmeringsprojekt\DDH2026\README.md` — setup, hardware topology, runbook, and validation procedure.
- `c:\Users\einar\Programmeringsprojekt\DDH2026\pyproject.toml` — Python project/dependency definition for the host-side pipeline.
- `c:\Users\einar\Programmeringsprojekt\DDH2026\src\kinetic_ranger\config.py` — radio, telemetry, and alert configuration.
- `c:\Users\einar\Programmeringsprojekt\DDH2026\src\kinetic_ranger\radio\capture.py` — AntSDR/libiio interface and IQ window acquisition.
- `c:\Users\einar\Programmeringsprojekt\DDH2026\src\kinetic_ranger\radio\features.py` — RSSI, CFO/Doppler proxy, SNR, and confidence extraction.
- `c:\Users\einar\Programmeringsprojekt\DDH2026\src\kinetic_ranger\telemetry\ingest.py` — autopilot/GPS log ingest and time alignment.
- `c:\Users\einar\Programmeringsprojekt\DDH2026\src\kinetic_ranger\estimation\ekf.py` — range/closing-rate estimator and uncertainty handling.
- `c:\Users\einar\Programmeringsprojekt\DDH2026\src\kinetic_ranger\alerting\rules.py` — closing-threat decision logic and hysteresis.
- `c:\Users\einar\Programmeringsprojekt\DDH2026\src\kinetic_ranger\logging\session_logger.py` — replayable experiment logs.
- `c:\Users\einar\Programmeringsprojekt\DDH2026\src\kinetic_ranger\ui\dashboard.py` — optional live dashboard for demo day.
- `c:\Users\einar\Programmeringsprojekt\DDH2026\tests\test_features.py` — unit tests for RSSI/CFO extraction on recorded samples.
- `c:\Users\einar\Programmeringsprojekt\DDH2026\tests\test_estimator.py` — simulation/replay tests for closing-rate and time-to-impact logic.

**Verification**

1. Radio bring-up: confirm the host can discover the E200, stream samples, and produce stable RSSI/CFO estimates on a static test transmitter at known distance.
2. Controlled motion sanity check: move the sensor along known paths relative to a fixed transmitter and confirm the system distinguishes approaching, receding, and lateral motion.
3. Offline replay: feed recorded observables and telemetry into the estimator and verify monotonic improvement of the closing-rate estimate over each approach run.
4. Alert evaluation: measure false positives on non-closing or lateral passes and verify alerts fire only on sustained closing trajectories.
5. Field demo: run at least one straight-in quadcopter approach with logged ground-truth distance/time markers and compare predicted time-to-impact against the observed approach timeline.
6. Robustness pass: repeat after gain changes, different antenna headings, and different start ranges to quantify how brittle the heuristic is under hackathon conditions.

**Decisions**

- Included: Linux host over Ethernet, AntSDR E200, directional antenna, quadcopter telemetry/GPS, host-side Python estimator, simple dashboard, replayable test logs.
- Included: MVP uses RSSI trend + CFO/Doppler proxy + ego-motion, not absolute high-accuracy ranging.
- Excluded from MVP: extra SDRs, TDOA, FPGA customization, phase-coherent ranging, full DOA beamforming, production-grade UI, and transmitter identification beyond “unknown radio closing rapidly.”
- Preferred software stack: Ubuntu 22.04, Python 3.11+, libiio/IIO first, NumPy/SciPy/Pandas for DSP and filtering, Matplotlib/Plotly for plots, optional GNU Radio for exploration only.
- Use fixed gain during experiments whenever possible; AGC makes RSSI-based ranging slippery.

**Further Considerations**

1. Signal choice recommendation: if you control the transmitter for validation, use a narrowband beacon or stable continuous waveform before trying unknown wideband emitters; this makes CFO extraction and ground-truth comparison much easier.
2. Antenna recommendation: a modest directional patch or Yagi is enough for MVP SNR gains; do not spend hackathon time building a calibrated array unless the MVP is already solid.
3. Time-to-impact recommendation: present it as an estimated interval with confidence or bands, not a single precise number, because unknown transmit power and multipath limit absolute accuracy.

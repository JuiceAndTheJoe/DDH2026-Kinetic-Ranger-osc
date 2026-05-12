## Revised Plan: Kinetic Ranger

Build a stationary, host-centric passive RF threat tracker around the AntSDR E200 that detects active emitters, characterizes them using spectral features, estimates direction using the E200’s two coherent RX channels, estimates approach or recession using Doppler or carrier offset trend, uses RSSI trend as a supporting cue rather than the primary truth source, and presents the result in a threat-centric operator UI.

### Why this merged version is stronger

From the two source plans:

- The characterization-and-tracking plan improves the physics and the demo story:
  - stationary sensor,
  - two-channel AOA,
  - Doppler-driven closing detection,
  - signal classification,
  - much stronger UI concept.

- The MVP scaffold plan improves execution discipline:
  - phased implementation,
  - logging/replay,
  - config-driven structure,
  - estimator/alert separation,
  - concrete verification steps.

The merged plan therefore uses the stationary AOA/Doppler sensing architecture together with the phased, testable engineering workflow.

### Phase 1 — Platform bring-up and observables foundation

1. Bring up the AntSDR E200 over Ethernet on the host.
   - Start with IIO/libiio-compatible workflows for fastest success.
   - Verify network connectivity, sample capture, stable tuning, fixed-gain operation, and dual-channel coherent receive path availability.

2. Keep the current Python project structure.
   - Preserve modules for radio capture, feature extraction, estimation/tracking, alerting, logging/replay, and UI.
   - Revise internal assumptions from “single-channel closure estimation with ego-motion” to “stationary sensor, multi-observable emitter tracking.”

3. Implement a spectrum sweep and band activity detector.
   - Sweep practical drone-relevant bands first.
   - Output persistent detections with center frequency, bandwidth, energy, dwell time, and confidence.

### Phase 2 — Two-channel direction finding

4. Enable coherent dual-RX capture.
   - Capture both receiver channels simultaneously.
   - Add explicit phase-offset calibration support using a splitter-based reference, loopback, or a known beacon.

5. Implement AOA estimation.
   - Start with a simple phase-difference-based AOA method for narrowband or compact signals.
   - Produce bearing estimate, bearing confidence, and calibration health indicators per detection.

6. Validate AOA on a known reference emitter.
   - Use a static beacon at known azimuth.
   - Treat this as a hard milestone. If AOA is unstable, temporarily fall back to characterization plus Doppler plus RSSI, while keeping AOA as the main goal.

### Phase 3 — Signal characterization and Doppler tracking

7. Expand observables beyond RSSI and CFO.
   For each emitter track, compute:
   - RSSI,
   - noise floor,
   - SNR,
   - spectral width,
   - burstiness or persistence,
   - CFO or Doppler proxy,
   - AOA,
   - AOA stability over time.

8. Add lightweight signal classification.
   - Use hand-tuned heuristics first, not heavy ML.
   - Classify signals as OFDM-like, FHSS-like, analog FM-like, narrowband beacon-like, and likely Wi‑Fi / ELRS / FPV / OcuSync-style classes where possible.

9. Implement Doppler or carrier trend tracking.
   - Track sign and magnitude stability.
   - Use this as the main cue for approaching, receding, and lateral or ambiguous motion.

### Phase 4 — Per-emitter tracking and threat scoring

10. Move from single-stream estimation to per-emitter tracking.
    - Maintain one tracker per persistent emitter.
    - Associate detections over time using frequency proximity, bandwidth similarity, AOA continuity, and temporal persistence.

11. Replace the current EKF target state with a more appropriate track state.
    The track state should emphasize:
    - bearing or AOA,
    - bearing rate,
    - Doppler or radial-velocity proxy,
    - RSSI trend,
    - classification confidence,
    - threat score.

    Optional:
    - Keep a range proxy or time-to-impact proxy, but present it as approximate and confidence-banded.

12. Define a composite threat indicator.
    Threat logic should combine:
    - AOA stability,
    - Doppler sign and magnitude,
    - RSSI growth rate,
    - track confidence,
    - classification relevance.

    Use RSSI as a useful cue, but gate it with AOA and Doppler so a transmitter power ramp is not mistaken for a closing threat.

### Phase 5 — Logging, replay, and validation harness

13. Extend logging to full replayability.
    Record:
    - raw or decimated IQ where practical,
    - sweep detections,
    - extracted observables,
    - per-emitter track state,
    - AOA calibration metadata,
    - alert decisions.

14. Support offline replay for detector → tracker → alert.
    - Use this to tune thresholds, debug association failures, compare threat-scoring methods, and rehearse demos without live hardware.

15. Validation progression.
    - static known emitter,
    - moving reference transmitter,
    - controlled straight-in approach,
    - lateral pass,
    - stationary power-ramping transmitter vs actual approach case.

### Phase 6 — Demo UI and operator experience

16. Build the operator UI around three views.
    - Polar threat scope: angle = AOA, radial distance = signal or range proxy, color = Doppler or threat.
    - Emitter dossier panel: band, bandwidth, modulation guess, classification, confidence.
    - Threat waterfall or spectrogram overlay: detected ribbons colored by AOA and motion status.

17. Add clear alert outputs.
    - threat ribbon,
    - alert history,
    - optional audio cue tied to closing rate or threat level.

18. Keep the console mode too.
    - It remains useful for field testing and as a fallback if the graphical UI is unavailable.

### Phase 7 — Demo packaging and scope control

19. Primary demo objective.
    Show that the system can:
    - detect an emitter,
    - classify it plausibly,
    - show its bearing,
    - determine whether it is approaching or not,
    - and raise a conservative alert for a fast-closing threat.

20. Explicit non-goals for MVP.
    Do not promise:
    - true absolute geolocation,
    - phase-coherent ranging,
    - TDOA,
    - synthetic aperture,
    - polished production UI,
    - large-scale ML classification,
    - FPGA changes.

### Best parts retained from each source plan

Kept from the characterization-and-tracking plan:
- stationary-sensor framing,
- two-channel AOA as a key differentiator,
- Doppler + RSSI + AOA fusion for threat detection,
- multi-emitter characterization mindset,
- strong operator-centered UI concept,
- the “power ramp vs real approach” demo narrative.

Kept from the MVP scaffold plan:
- phased delivery,
- config-driven Python package structure,
- logging/replay workflow,
- unit-testable modules,
- conservative alerting with hysteresis,
- clear validation progression,
- scope discipline and MVP exclusions.

### Current project alignment

The current project structure is still a good fit for this revised plan. The existing modules for radio capture, feature extraction, estimation, alerting, telemetry, logging, and UI can all be reused.

However, the current implementation is still centered on the earlier closure MVP:
- one stream,
- one emitter,
- one observation per window,
- one EKF state with range, closing rate, and effective power,
- a simpler single-channel live path,
- no AOA model,
- no dual-channel calibration,
- no multi-emitter association,
- and only a console-style UI.

So the project setup is structurally reusable, but the sensing and tracking model should pivot from “host-motion closure estimator” to “stationary passive threat tracker with AOA + Doppler + characterization.”

### Practical implementation priority

Recommended order of work:
1. dual-channel capture and phase calibration,
2. AOA estimation,
3. band sweep and persistent detections,
4. per-emitter tracking,
5. Doppler/RSSI threat scoring,
6. UI polish and classifier heuristics.

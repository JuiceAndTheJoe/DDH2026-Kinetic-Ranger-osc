# Claude Plan — Passive Emitter Characterization & Tracking

Good clarification — that pivots the project from "passive emitter geolocation" toward "passive emitter *characterization and tracking* with insightful display." It actually makes the engineering more tractable and the demo more impressive, and it plays to the E200's real strengths.

## What changes physically

A stationary sensor with no active emission can't, in the strict mathematical sense, recover absolute range from a single isotropic RSSI observation of an unknown transmitter — that's the Tx-power ambiguity from before. But you don't need true range to satisfy "is this thing closing in fast?" You need three things, all of which a stationary E200 gives you cleanly:

1. **Direction** (AOA) — from the two coherent RX channels with a short antenna baseline.
2. **Radial velocity sign and magnitude** — from Doppler on the carrier or pilot.
3. **Closing-rate proxy** — from RSSI growth rate, gated by Doppler so you don't get fooled by a transmitter that's simply ramping its power.

What's gone from the previous brief: synthetic aperture, bearings-only with a maneuvering observer, virtual-array TDOA. What stays and gets more important: the **spectrum-sweep front end**, the **two-channel AOA**, the **Doppler tracker**, and the **drone-signature catalog** (DJI OcuSync, FPV analog, ELRS, etc.) for identifying what the emitter actually is.

## The physics of "closing fast" from a fixed point

For a drone moving with velocity **v** at slant range r and bearing θ (LOS-to-velocity angle α):

- Doppler shift: f_d = − (v cos α) · f_c / c. Sign of f_d immediately tells you closing vs. receding.
- AOA rate: dθ/dt = (v sin α) / r. A head-on approach has dθ/dt ≈ 0 with strong negative range-rate; a fly-by has large dθ/dt and small Doppler magnitude.
- RSSI growth: dP/dt ∝ −10n/r · dr/dt. Steep positive slope + AOA stable + positive Doppler ≡ "incoming, head-on."

The product **(AOA stability) × (RSSI slope) × (Doppler sign)** is essentially the threat indicator. You can compute a time-to-impact from RSSI doubling time alone if you assume a plausible drone speed (10–25 m/s for most quads), and refine it when Doppler magnitude gives you the actual radial velocity.

## Where to spend the week: characterization + visualization

The center of gravity becomes the **operator view**. Three pieces of UX make this stand out from a typical hackathon RF demo:

**(1) A polar threat scope.** AOA on the angle axis, RSSI (or estimated range proxy) on the radial axis, color-coded by Doppler. Approaching = warm red, receding = cool blue, static = grey. Trails show recent history so the eye reads motion immediately. This is the centerpiece visualization.

**(2) An emitter dossier panel.** When the detector locks onto a signal, show its band, instantaneous bandwidth, modulation guess (OFDM / FHSS / analog FM / LoRa), and best-guess class ("looks like OcuSync 3 video downlink," "looks like ExpressLRS 2.4"). This makes the system feel intelligent without needing a heavy ML stack — most drone emissions are spectrally distinctive enough that a hand-tuned classifier nails them.

**(3) A threat ribbon / spectrogram with overlays.** Standard waterfall, but every persistent emitter gets a colored ribbon overlay encoding AOA (hue) and Doppler (saturation). At a glance you see all active emitters, their directions, and which ones are moving toward you.

Plus an audible cue — pitch tied to closing rate, sonar-pinger style. It's the difference between a tech demo and something a judge can imagine in an actual ops room.

Here's a concrete mockup of the threat scope to anchor the discussion: the polar scope is the demo centerpiece, but two more views are worth building alongside it:

A **time-frequency-bearing waterfall** — a standard spectrogram, but every detected emitter ribbon is tinted by its current AOA (hue) and its current Doppler (saturation or width). It compresses an enormous amount of state into one display: "this OFDM lump in 5.8 GHz has been hot for 8 seconds, it's slightly north-east, and it just started showing positive Doppler." Operators read it instantly.

A **target trajectory plot** — small inset showing the EKF state trajectory in (bearing, range-proxy) space with a 1σ uncertainty ellipse. Lets you see the filter converging and shows that the system has a real internal model, not just thresholds.

## Revised week plan

The shift to stationary makes a few days easier and a few days harder. Specifically:

- **Day 1**: Bring up E200 over GbE, capture 20 MHz windows across 400 MHz–6 GHz with a Python sweeper. Build a simple energy detector that lists active bands.
- **Day 2**: Two-channel coherent capture; calibrate phase offset using a splitter or the on-chip TX → RX loopback; verify AOA on a known-direction beacon (a Pluto or HackRF emitting a tone from a tripod 20 m away). This is the make-or-break milestone — if AOA works, the whole project flies.
- **Day 3**: Per-band signal classifiers (bandwidth, modulation, burst pattern → "looks like OcuSync / FPV / ELRS / Wi-Fi"). Build the spectral dossier panel.
- **Day 4**: Doppler tracker (FFT-peak track or PLL on the carrier/pilot) and RSSI trender. Validate against the Pluto-on-a-string or a known drone walking in.
- **Day 5**: Stitch detection → AOA → Doppler → RSSI into a single tracker per emitter, with a simple state estimator. Wire to a web UI (Flask + websockets is fastest for hackathon-grade real-time).
- **Day 6**: Polish the threat scope, add the waterfall view with AOA tinting, hook up the audio alert, integrate the alert thresholds.
- **Day 7**: Three full demo dry-runs with a flying drone. Capture video. Write the one-page judges' brief.

## Two things to nail for the demo

The **AOA calibration** matters more than anything else technically — if the two channels aren't phase-aligned, every direction estimate is garbage. Budget a half-day for it specifically, with a known-position reference emitter.

The **Tx-power disambiguation moment** is your strongest narrative beat. Plan a deliberate part of the demo where a stationary transmitter ramps its power while a different drone closes in. Your scope shows the ramper sitting still (gray, static), and the drone painting red and tracking inward. That single demo moment is worth more than ten minutes of slides.

The previous artifact still has the useful pieces — E200 specs, drone signature catalog, libraries to start from, the alphafox02 / WarDragon ecosystem — just mentally cross out the synthetic-aperture and maneuvering-observer sections.

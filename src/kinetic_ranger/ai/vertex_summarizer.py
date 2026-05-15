import os
from typing import List, Optional

import vertexai
from vertexai.generative_models import GenerativeModel

PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
MODEL = os.getenv("GOOGLE_GENAI_MODEL", "gemini-2.5-flash")


def ai_summaries_enabled() -> bool:
    return os.getenv("KR_AI_SUMMARIES_ENABLED", "false").lower() == "true"


class VertexAISummarizer:
    def __init__(
        self,
        project: Optional[str] = None,
        location: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.project = project or PROJECT
        self.location = location or LOCATION
        self.model = model or MODEL

    def _generate(self, prompt: str, location: str) -> str:
        vertexai.init(project=self.project, location=location)
        gemini = GenerativeModel(self.model)
        response = gemini.generate_content(prompt)
        return response.text.strip()

    def summarize_run(self, run_facts: dict) -> str:
        """Summarize one replay run using precomputed authoritative facts."""
        if not run_facts.get("total_frames"):
            return "No events to summarize."
        prompt = self._format_prompt(run_facts)
        fallback_summary = self._deterministic_summary(run_facts)
        try:
            response = self._generate(prompt, self.location)
            return self._validated_summary(response, run_facts, fallback_summary)
        except Exception as e:
            message = str(e)
            if self.location != "global" and "501" in message and (
                "not implemented" in message.lower()
                or "not supported" in message.lower()
                or "not enabled" in message.lower()
            ):
                try:
                    response = self._generate(prompt, "global")
                    return self._validated_summary(response, run_facts, fallback_summary)
                except Exception as fallback_error:
                    return fallback_summary
            return fallback_summary

    def summarize_events(self, events: List[dict]) -> str:
        """Backward-compatible helper for older callers that only have raw events."""
        if not events:
            return "No events to summarize."
        ttc_values = [float(e["ttc"]) for e in events if e.get("ttc") is not None]
        active_ttc_values = [
            float(e["ttc"]) for e in events if e.get("active") and e.get("ttc") is not None
        ]
        run_facts = {
            "run_id": "unknown",
            "total_frames": len(events),
            "duration_s": round(max(events[-1]["time"] - events[0]["time"], 0.0), 2),
            "peak_severity": max((e.get("threat", "info") for e in events), key=lambda s: {"info": 1, "warning": 2, "critical": 3}.get(s, 0)),
            "peak_threat_level": "HIGH",
            "active_alert_frames": sum(1 for e in events if e.get("active")),
            "active_alert_ratio": 0.0,
            "signal_trend": "strengthening" if events[-1].get("rssi_db", 0.0) > events[0].get("rssi_db", 0.0) else "stable",
            "start_rssi_db": round(events[0].get("rssi_db", 0.0), 2),
            "end_rssi_db": round(events[-1].get("rssi_db", 0.0), 2),
            "peak_rssi_db": round(max(e.get("rssi_db", 0.0) for e in events), 2),
            "min_ttc_s": min(ttc_values) if ttc_values else None,
            "min_ttc_during_alert_s": min(active_ttc_values) if active_ttc_values else None,
            "first_alert_time_s": next((round(e.get("time", 0.0), 2) for e in events if e.get("active")), None),
            "reasons_seen": [],
            "highlights": [],
        }
        severity = run_facts["peak_severity"]
        run_facts["peak_threat_level"] = {
            "critical": "CRITICAL",
            "warning": "HIGH",
            "info": "LOW",
        }.get(severity, "LOW")
        if run_facts["total_frames"]:
            run_facts["active_alert_ratio"] = round(
                run_facts["active_alert_frames"] / run_facts["total_frames"], 3
            )
        return self.summarize_run(run_facts)

    def _format_prompt(self, run_facts: dict) -> str:
        highlight_lines = []
        for item in run_facts.get("highlights", []):
            ttc = f"{item['ttc_s']:.2f}s" if item.get("ttc_s") is not None else "unknown"
            state = "ALERT" if item.get("alert_active") else "tracking"
            highlight_lines.append(
                f"- t={item['time_s']:.2f}s frame={item['frame_index']} "
                f"severity={item['severity']} threat={item['threat_level']} "
                f"state={state} ttc={ttc} rssi={item['rssi_db']:.2f}dBFS reason={item['reason']}"
            )
        alert_active = run_facts.get("active_alert_frames", 0) > 0
        return (
            "You are an RF threat analyst assistant. "
            "Summarize the replay using ONLY the facts below. "
            "Never downgrade or contradict the stated peak threat level. "
            "If peak_threat_level is HIGH or CRITICAL, explicitly say that. "
            "Be concise: 2-4 sentences, operator-facing, no bullet points. "
            "Do NOT mention frame counts, frame numbers, raw RSSI values, or any other "
            "internal technical metadata — only use human-readable operational details "
            "(threat level, timing in seconds, signal trend, time-to-collision).\n\n"
            f"duration_s: {run_facts['duration_s']}\n"
            f"peak_threat_level: {run_facts['peak_threat_level']}\n"
            f"alert_active: {alert_active}\n"
            f"first_alert_time_s: {run_facts['first_alert_time_s']}\n"
            f"min_ttc_s: {run_facts['min_ttc_s']}\n"
            f"min_ttc_during_alert_s: {run_facts['min_ttc_during_alert_s']}\n"
            f"signal_trend: {run_facts['signal_trend']}\n"
            f"reasons_seen: {', '.join(run_facts.get('reasons_seen', []))}\n\n"
            "Highlights:\n" + "\n".join(highlight_lines)
        )

    def _deterministic_summary(self, run_facts: dict) -> str:
        peak_threat = run_facts["peak_threat_level"]
        min_ttc = run_facts.get("min_ttc_s")
        min_alert_ttc = run_facts.get("min_ttc_during_alert_s")
        active_frames = run_facts.get("active_alert_frames", 0)
        trend = run_facts.get("signal_trend", "stable")

        first_alert_time = run_facts.get("first_alert_time_s")

        if active_frames > 0 and first_alert_time is not None:
            first_sentence = (
                f"A {peak_threat} threat was detected, with an active alert triggered at "
                f"{first_alert_time:.1f} seconds into the recording."
            )
        elif active_frames > 0:
            first_sentence = f"A {peak_threat} threat was detected and triggered an active alert."
        else:
            first_sentence = (
                f"A {peak_threat} threat level was reached but did not sustain long enough to trigger an active alert."
            )

        effective_ttc = min_alert_ttc if min_alert_ttc is not None else min_ttc
        if effective_ttc is not None:
            second_sentence = f"The closest estimated time to collision was {effective_ttc:.1f} seconds."
        else:
            second_sentence = "No time-to-collision estimate was available during this recording."

        third_sentence = f"The signal was {trend} throughout the recording."
        return " ".join([first_sentence, second_sentence, third_sentence])

    def _validated_summary(self, text: str, run_facts: dict, fallback_summary: str) -> str:
        normalized = text.strip()
        if not normalized:
            return fallback_summary
        lower = normalized.lower()
        peak = run_facts.get("peak_threat_level", "LOW")
        active_frames = run_facts.get("active_alert_frames", 0)

        if peak == "CRITICAL" and "critical" not in lower:
            return fallback_summary
        if peak == "HIGH" and not any(token in lower for token in ["high", "warning"]):
            return fallback_summary
        if active_frames == 0 and any(token in lower for token in ["critical threat", "high threat"]):
            return fallback_summary
        return normalized

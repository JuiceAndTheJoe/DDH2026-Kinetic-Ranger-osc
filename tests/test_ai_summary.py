import os
import pytest
from fastapi.testclient import TestClient

from kinetic_ranger.ai.vertex_summarizer import VertexAISummarizer
from kinetic_ranger.api.ai_summary import _build_run_facts
from kinetic_ranger.api.main import app
from kinetic_ranger.models import AlertDecision, RadioObservation, ThreatEstimate

@pytest.fixture(autouse=True)
def enable_ai_summary(monkeypatch):
    monkeypatch.setenv("KR_AI_SUMMARIES_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "dummy"))
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", os.getenv("GOOGLE_CLOUD_LOCATION", "global"))
    monkeypatch.setenv("GOOGLE_GENAI_MODEL", os.getenv("GOOGLE_GENAI_MODEL", "gemini-2.5-flash"))

def test_ai_summary_disabled(monkeypatch):
    monkeypatch.setenv("KR_AI_SUMMARIES_ENABLED", "false")
    with TestClient(app) as client:
        response = client.get("/runs/fake_run/ai_summary")
    assert response.status_code == 403

def test_ai_summary_not_found():
    with TestClient(app) as client:
        response = client.get("/runs/fake_run/ai_summary")
    assert response.status_code == 404 or response.status_code == 403


def _snapshot(time_s: float, rssi_db: float, ttc_s: float | None, active: bool, severity: str):
    observation = RadioObservation(
        timestamp_s=time_s,
        center_frequency_hz=2.4e9,
        rssi_dbfs=rssi_db,
        cfo_hz=0.0,
        snr_db=12.0,
        confidence=0.95,
    )
    estimate = ThreatEstimate(
        timestamp_s=time_s,
        rssi_dbfs=rssi_db,
        rssi_slope_db_per_s=1.5,
        closing_rate_mps=-8.0,
        time_to_impact_s=ttc_s,
        covariance_diag=(1.0, 1.0, 1.0),
        confidence=0.96,
    )
    alert = AlertDecision(
        timestamp_s=time_s,
        active=active,
        severity=severity,
        reason="test",
        sustained_hits=3 if active else 0,
        cooldown_remaining_s=0.0,
    )
    return observation, estimate, alert, None, None


def test_build_run_facts_tracks_peak_threat_not_majority_label():
    snapshots = [
        _snapshot(0.0, -71.0, 18.0, False, "info"),
        _snapshot(1.0, -68.0, 14.1, False, "info"),
        _snapshot(2.0, -63.0, 9.2, True, "warning"),
        _snapshot(3.0, -59.0, 7.8, True, "warning"),
        _snapshot(4.0, -58.0, 11.0, False, "info"),
    ]

    facts = _build_run_facts("run-1", snapshots)

    assert facts["peak_severity"] == "warning"
    assert facts["peak_threat_level"] == "HIGH"
    assert facts["active_alert_frames"] == 2
    assert facts["min_ttc_s"] == 7.8
    assert facts["min_ttc_during_alert_s"] == 7.8
    assert facts["signal_trend"] == "strengthening"


def test_validated_summary_falls_back_when_model_downgrades_peak_threat():
    summarizer = VertexAISummarizer(project="dummy", location="global", model="dummy")
    run_facts = {
        "run_id": "run-1",
        "total_frames": 5,
        "duration_s": 4.0,
        "peak_severity": "warning",
        "peak_threat_level": "HIGH",
        "active_alert_frames": 2,
        "active_alert_ratio": 0.4,
        "first_alert_time_s": 2.0,
        "min_ttc_s": 7.8,
        "min_ttc_during_alert_s": 7.8,
        "signal_trend": "strengthening",
        "start_rssi_db": -71.0,
        "end_rssi_db": -58.0,
        "peak_rssi_db": -58.0,
        "reasons_seen": ["test"],
        "highlights": [],
    }

    fallback = summarizer._deterministic_summary(run_facts)
    validated = summarizer._validated_summary(
        "A drone maintained a consistent info threat level throughout the observation.",
        run_facts,
        fallback,
    )

    assert validated == fallback
    assert "HIGH" in validated

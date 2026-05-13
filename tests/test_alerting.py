from __future__ import annotations

from kinetic_ranger.alerting.rules import AlertRuleEngine
from kinetic_ranger.config import AlertConfig
from kinetic_ranger.models import RadioObservation, ThreatEstimate


def test_alert_engine_requires_sustained_hits() -> None:
    config = AlertConfig(consecutive_hits=2, min_confidence=0.5, min_closing_rate_mps=2.0, tti_threshold_s=12.0)
    engine = AlertRuleEngine(config)

    first_estimate = ThreatEstimate(
        timestamp_s=0.0,
        rssi_dbfs=-40.0,
        rssi_slope_db_per_s=1.5,
        closing_rate_mps=-4.0,
        time_to_impact_s=6.25,
        covariance_diag=(4.0, 1.0, 1.0),
        confidence=0.8,
    )
    second_estimate = ThreatEstimate(
        timestamp_s=1.0,
        rssi_dbfs=-38.0,
        rssi_slope_db_per_s=1.8,
        closing_rate_mps=-4.2,
        time_to_impact_s=5.0,
        covariance_diag=(4.0, 1.0, 1.0),
        confidence=0.82,
    )
    observation = RadioObservation(
        timestamp_s=0.0,
        center_frequency_hz=2_437_000_000.0,
        rssi_dbfs=-45.0,
        cfo_hz=30.0,
        snr_db=18.0,
        confidence=0.8,
        noise_floor_dbfs=-65.0,
        agc_enabled=False,
        spectral_width_hz=2_000.0,
    )

    first_decision = engine.evaluate(first_estimate, observation)
    second_decision = engine.evaluate(second_estimate, observation)

    assert not first_decision.active
    assert second_decision.active
    assert second_decision.severity in {"warning", "critical"}

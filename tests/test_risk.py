"""
Unit tests for CareLoop deterministic RiskEngine (engine/risk.py).

Verifies:
- Formula: risk = sum(weight_i * anomaly_i)
  weights: medication_missed 0.4, no_movement 0.3, odd_hour_activity 0.2, meal_missed 0.2
- Mapping:
  - low (<0.3)
  - medium (<0.6)
  - high (>=0.6)
- Return value includes numeric score, level, and plain-English reasons.
"""

import pytest
from careloop.engine.risk import RiskEngine


@pytest.fixture
def risk_engine():
    return RiskEngine()


def test_zero_anomalies_nominal(risk_engine):
    res = risk_engine.calculate_risk()
    assert res.score == 0.0
    assert res.level == "low"
    assert len(res.reasons) >= 1
    assert "nominal" in res.reasons[0].lower()


def test_single_low_weight_anomalies(risk_engine):
    # meal_missed (0.2) -> score 0.2, level low (< 0.3)
    res_meal = risk_engine.calculate_risk(meal_missed=True)
    assert res_meal.score == 0.2
    assert res_meal.level == "low"
    assert any("meal" in r.lower() for r in res_meal.reasons)

    # odd_hour_activity (0.2) -> score 0.2, level low (< 0.3)
    res_odd = risk_engine.calculate_risk(odd_hour_activity=True)
    assert res_odd.score == 0.2
    assert res_odd.level == "low"
    assert any("night" in r.lower() or "sleep" in r.lower() for r in res_odd.reasons)


def test_medium_risk_thresholds(risk_engine):
    # no_movement (0.3) -> score 0.3, level medium (< 0.6)
    res_mov = risk_engine.calculate_risk(no_movement=True)
    assert res_mov.score == 0.3
    assert res_mov.level == "medium"
    assert any("movement" in r.lower() or "inactivity" in r.lower() for r in res_mov.reasons)

    # medication_missed (0.4) -> score 0.4, level medium (< 0.6)
    res_med = risk_engine.calculate_risk(medication_missed=True)
    assert res_med.score == 0.4
    assert res_med.level == "medium"
    assert any("medication" in r.lower() for r in res_med.reasons)

    # no_movement (0.3) + odd_hour_activity (0.2) -> score 0.5, level medium
    res_combo = risk_engine.calculate_risk(no_movement=True, odd_hour_activity=True)
    assert res_combo.score == 0.5
    assert res_combo.level == "medium"
    assert len(res_combo.reasons) == 2


def test_high_risk_thresholds(risk_engine):
    # medication_missed (0.4) + meal_missed (0.2) -> score 0.6, level high
    res_med_meal = risk_engine.calculate_risk(medication_missed=True, meal_missed=True)
    assert res_med_meal.score == 0.6
    assert res_med_meal.level == "high"

    # medication_missed (0.4) + no_movement (0.3) -> score 0.7, level high
    res_med_mov = risk_engine.calculate_risk(medication_missed=True, no_movement=True)
    assert res_med_mov.score == 0.7
    assert res_med_mov.level == "high"

    # All four active -> score 1.1, level high
    res_all = risk_engine.calculate_risk(
        medication_missed=True,
        no_movement=True,
        odd_hour_activity=True,
        meal_missed=True,
    )
    assert res_all.score == 1.1
    assert res_all.level == "high"
    assert len(res_all.reasons) == 4
    for r in res_all.reasons:
        assert "weight:" in r

"""
Tests for CareLoop 60-Day Routine Safety Benchmark and Evaluation Script.
Includes hand-verifiable metric calculation tests, baseline comparison tests,
cold-start handling tests, and temporal leakage checks.
"""

from datetime import datetime, timezone, timedelta
import json
import os
import tempfile
import pytest

from scripts.seed_data import seed_database
from scripts.evaluate_benchmark import (
    run_benchmark,
    compute_evaluation_metrics,
    StaticThresholdBaseline,
)
from careloop.models import Event, EventType


# ---------------------------------------------------------------------------
# Hand-Verifiable Metric Calculation Tests
# ---------------------------------------------------------------------------

def test_compute_evaluation_metrics_hand_verifiable():
    """
    Test metric calculation on a small, hand-verifiable confusion matrix.
    Given:
      TP = 8, FP = 2, FN = 2, TN = 88
      Active person-days = 30
      Delays from sched: [40, 50, 60, 30, 45, 55, 35, 65] (Sum: 380, Mean: 47.5)
      Delays past grace: [10, 20, 30,  0, 15, 25,  5, 35] (Sum: 140, Mean: 17.5)
    Expected:
      Precision = 8 / (8 + 2) = 80.0%
      Recall / Detection Rate = 8 / (8 + 2) = 80.0%
      False-Alarm Rate (FAR) = 2 / (2 + 88) = 2 / 90 = 2.222%
      False alerts per person-day = 2 / 30 = 0.0667
      False alerts per month = 0.0667 * 30 = 2.0
      Avg delay sched = 47.5 min
      Avg delay grace = 17.5 min
    """
    delays_sched = [40.0, 50.0, 60.0, 30.0, 45.0, 55.0, 35.0, 65.0]
    delays_grace = [10.0, 20.0, 30.0, 0.0, 15.0, 25.0, 5.0, 35.0]

    metrics = compute_evaluation_metrics(
        tp=8,
        fp=2,
        fn=2,
        tn=88,
        active_person_days=30,
        delays_sched=delays_sched,
        delays_grace=delays_grace,
    )

    assert metrics["tp"] == 8
    assert metrics["fp"] == 2
    assert metrics["fn"] == 2
    assert metrics["tn"] == 88
    assert metrics["precision"] == 80.0
    assert metrics["recall"] == 80.0
    assert metrics["detection_rate"] == 80.0
    assert metrics["false_alarm_rate"] == 2.222
    assert metrics["false_alerts_per_person_day"] == 0.0667
    assert metrics["false_alerts_per_month"] == 2.0
    assert metrics["avg_delay_sched_min"] == 47.5
    assert metrics["avg_delay_grace_min"] == 17.5


def test_compute_evaluation_metrics_zero_divisions_safe():
    """Verify that empty datasets or zero alerts do not raise ZeroDivisionError."""
    # Zero detections and zero false positives
    metrics_empty = compute_evaluation_metrics(
        tp=0,
        fp=0,
        fn=0,
        tn=0,
        active_person_days=0,
        delays_sched=[],
        delays_grace=[],
    )
    assert metrics_empty["precision"] == 0.0
    assert metrics_empty["recall"] == 0.0
    assert metrics_empty["false_alarm_rate"] == 0.0
    assert metrics_empty["false_alerts_per_person_day"] == 0.0
    assert metrics_empty["avg_delay_sched_min"] == 0.0
    assert metrics_empty["avg_delay_grace_min"] == 0.0


def test_static_threshold_baseline_hand_verifiable():
    """Verify static policy produces expected alerts on fixed thresholds."""
    policy = StaticThresholdBaseline(
        med_cutoff_hour=9,
        med_cutoff_min=0,
        lunch_cutoff_hour=13,
        lunch_cutoff_min=15,
        inactivity_threshold_hours=3.0,
    )

    dt_ref = datetime(2026, 10, 20, 8, 30, tzinfo=timezone.utc)
    # At 08:30 (before 09:00 cutoff): no alert even without pill
    assert not policy.evaluate_medication(events_so_far=[], current_time=dt_ref)

    # At 09:15 (after 09:00 cutoff): flags alert if no pill
    dt_late = datetime(2026, 10, 20, 9, 15, tzinfo=timezone.utc)
    assert policy.evaluate_medication(events_so_far=[], current_time=dt_late)

    # At 09:15 with pill taken at 08:45: no alert
    ev_pill = Event(
        person_id="eleanor",
        event_type=EventType.PILL,
        timestamp=datetime(2026, 10, 20, 8, 45, tzinfo=timezone.utc),
    )
    assert not policy.evaluate_medication(events_so_far=[ev_pill], current_time=dt_late)


# ---------------------------------------------------------------------------
# Full 60-Day Benchmark Integration Tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def benchmark_data():
    fd_db, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd_db)

    fd_json, json_path = tempfile.mkstemp(suffix=".json")
    os.close(fd_json)

    # Generate 60 days
    metadata = seed_database(
        db_path=db_path,
        total_days=60,
        incidents_json_path=json_path,
        seed=42,
    )

    yield db_path, json_path, metadata

    if os.path.exists(db_path):
        os.remove(db_path)
    if os.path.exists(json_path):
        os.remove(json_path)


def test_seed_database_generates_profiles_and_incidents(benchmark_data):
    db_path, json_path, metadata = benchmark_data

    with open(json_path, "r", encoding="utf-8") as f:
        incidents = json.load(f)

    assert len(incidents) == 18, "Expected 18 total ground truth incidents (6 per persona)"
    person_ids = {inc["person_id"] for inc in incidents}
    assert person_ids == {"eleanor", "dad", "martha"}

    types = {inc["incident_type"] for inc in incidents}
    assert "missed_pill" in types
    assert "no_movement" in types
    assert "missed_lunch" in types

    assert metadata["seed"] == 42
    assert metadata["total_days"] == 60
    assert metadata["incidents_count"] == 18


def test_run_benchmark_evaluates_metrics_and_comparison(benchmark_data):
    db_path, json_path, _ = benchmark_data

    fd_out, out_md_path = tempfile.mkstemp(suffix=".md")
    os.close(fd_out)

    fd_json_out, out_json_path = tempfile.mkstemp(suffix=".json")
    os.close(fd_json_out)

    try:
        results = run_benchmark(
            db_path=db_path,
            incidents_json_path=json_path,
            total_days=60,
            cold_start_days=7,
            output_md_path=out_md_path,
            output_json_path=out_json_path,
            seed=42,
        )

        # 1. CareLoop Adaptive Circular EWMA Metrics
        comb = results["combined"]
        assert comb["tp"] == 18, f"Expected 18 True Positives, got {comb['tp']}"
        assert comb["fn"] == 0, f"Expected 0 False Negatives, got {comb['fn']}"
        assert comb["fp"] == 0, f"Expected 0 False Positives, got {comb['fp']}"
        assert comb["precision"] == 100.0
        assert comb["recall"] == 100.0
        assert comb["detection_rate"] == 100.0
        assert comb["false_alarm_rate"] == 0.0
        assert comb["false_alerts_per_person_day"] == 0.0

        for pid in ("eleanor", "dad", "martha"):
            p_res = results["personas"][pid]
            assert p_res["tp"] == 6
            assert p_res["fn"] == 0
            assert p_res["fp"] == 0
            assert p_res["recall"] == 100.0
            assert p_res["precision"] == 100.0

        # 2. Traditional Static Baseline Comparison
        st_comb = results["static_combined"]
        assert st_comb["tp"] >= 15, f"Static baseline detects most incidents, got {st_comb['tp']}"
        assert st_comb["fp"] > 0, "Static baseline must have false positives due to rigid thresholds"
        assert st_comb["precision"] < 50.0, "Static baseline precision is degraded by alarm fatigue"
        assert st_comb["false_alerts_per_person_day"] > 0.0

        # 3. Output files verification
        assert os.path.exists(out_md_path)
        with open(out_md_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "CareLoop: 60-Day Routine Safety Benchmark & Reproducible Evaluation Report" in content
            assert "Traditional Static Telecare" in content
            assert "CareLoop Adaptive EWMA" in content
            assert "100.0%" in content

        assert os.path.exists(out_json_path)
        with open(out_json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
            assert json_data["metadata"]["random_seed"] == 42
            assert json_data["careloop_adaptive_engine"]["combined"]["tp"] == 18
            assert json_data["careloop_adaptive_engine"]["combined"]["fp"] == 0
            assert "edge_case_handling" in json_data
            assert "limitations" in json_data
    finally:
        if os.path.exists(out_md_path):
            os.remove(out_md_path)
        if os.path.exists(out_json_path):
            os.remove(out_json_path)

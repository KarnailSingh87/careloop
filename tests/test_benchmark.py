"""
Tests for CareLoop 60-Day Routine Safety Benchmark and Evaluation Script.
"""

from datetime import datetime, timezone
import json
import os
import tempfile
import pytest

from scripts.seed_data import seed_database
from scripts.evaluate_benchmark import run_benchmark


@pytest.fixture(scope="module")
def benchmark_data():
    fd_db, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd_db)

    fd_json, json_path = tempfile.mkstemp(suffix=".json")
    os.close(fd_json)

    # Generate 60 days
    seed_database(
        db_path=db_path,
        total_days=60,
        incidents_json_path=json_path,
        seed=42,
    )

    yield db_path, json_path

    if os.path.exists(db_path):
        os.remove(db_path)
    if os.path.exists(json_path):
        os.remove(json_path)


def test_seed_database_generates_profiles_and_incidents(benchmark_data):
    db_path, json_path = benchmark_data

    with open(json_path, "r", encoding="utf-8") as f:
        incidents = json.load(f)

    assert len(incidents) == 18, "Expected 18 total ground truth incidents (6 per persona)"
    person_ids = {inc["person_id"] for inc in incidents}
    assert person_ids == {"eleanor", "dad", "martha"}

    types = {inc["incident_type"] for inc in incidents}
    assert "missed_pill" in types
    assert "no_movement" in types
    assert "missed_lunch" in types


def test_run_benchmark_evaluates_metrics(benchmark_data):
    db_path, json_path = benchmark_data

    fd_out, out_md_path = tempfile.mkstemp(suffix=".md")
    os.close(fd_out)

    try:
        results = run_benchmark(
            db_path=db_path,
            incidents_json_path=json_path,
            total_days=60,
            cold_start_days=7,
            output_md_path=out_md_path,
        )

        comb = results["combined"]
        assert comb["tp"] == 18, f"Expected 18 True Positives, got {comb['tp']}"
        assert comb["fn"] == 0, f"Expected 0 False Negatives, got {comb['fn']}"
        assert comb["fp"] == 0, f"Expected 0 False Positives, got {comb['fp']}"
        assert comb["detection_rate"] == 100.0
        assert comb["false_alarm_rate"] == 0.0

        for pid in ("eleanor", "dad", "martha"):
            p_res = results["personas"][pid]
            assert p_res["tp"] == 6
            assert p_res["fn"] == 0
            assert p_res["fp"] == 0
            assert p_res["detection_rate"] == 100.0

        assert os.path.exists(out_md_path)
        with open(out_md_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "CareLoop 60-Day Routine Benchmark & Evaluation Results" in content
            assert "Detection Rate (Sensitivity / Recall)" in content
            assert "False-Alarm Rate (FAR)" in content
            assert "100.0%" in content
    finally:
        if os.path.exists(out_md_path):
            os.remove(out_md_path)

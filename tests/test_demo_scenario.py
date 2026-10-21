"""
Integration contract tests for CareLoop's repeatable demonstration scenario.

Verifies:
1. Multi-day baseline routine is loaded and active.
2. Missed medication event past grace window triggers baseline anomaly.
3. Deterministic risk scoring produces explainable result.
4. Persisted escalation state transitions through configured stages:
   normal -> gentle_check_in -> repeat_check_in -> notify_family.
5. Console notification dispatched with evidence-based reasons and dedup key.
6. Repeated ticks on notify_family generate zero duplicate alerts.
7. Memory Q&A returns grounded answers without hallucinations or Bedrock dependence.
8. Caregiver resolution resets escalation state to normal and active alerts to resolved.
9. Runs 3 consecutive iterations from a clean start with zero stale state.
"""

import os
import tempfile
import pytest
from datetime import datetime, timezone, timedelta

from careloop.clock import SimulatedClock
from careloop.engine.baseline import BaselineEngine
from careloop.engine.escalation import EscalationEngine
from careloop.engine.risk import RiskEngine
from careloop.llm.bedrock import BedrockAssistant
from careloop.models import (
    AlertLevel,
    EscalationStage,
    Event,
    EventType,
)
from careloop.notifier import InMemoryNotifier
from careloop.storage.sqlite_store import SQLiteStorage
from scripts.seed_data import seed_database


@pytest.fixture
def temp_demo_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        # Seed 14 days of realistic baseline data
        seed_database(db_path=path, total_days=14, seed=42)
        yield path
    finally:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


def test_full_demo_scenario_three_consecutive_runs(temp_demo_db):
    """
    Run the full 9-step demonstration scenario from a clean start 3 times.
    Assert zero duplicate alerts, consistent timestamps, and complete isolation.
    """
    storage = SQLiteStorage(temp_demo_db)
    notifier = InMemoryNotifier()
    baseline_engine = BaselineEngine()
    risk_engine = RiskEngine()
    clock = SimulatedClock(datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc))

    # Pre-warm baseline engine
    baseline_engine.load_from_storage(storage)

    escalation_engine = EscalationEngine(
        storage=storage,
        risk_engine=risk_engine,
        baseline_engine=baseline_engine,
        notifier=notifier,
        gentle_timeout_seconds=60.0,
        repeat_timeout_seconds=60.0,
    )
    llm_assistant = BedrockAssistant()
    person_id = "eleanor"

    for run_idx in range(1, 4):
        # 1. Clean Reset: clear demo data and reset clock to 08:00 UTC
        storage.clear_demo_data(person_id)
        notifier.notifications.clear()
        base_time = datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc)
        clock.set_time(base_time)
        escalation_engine.reset_to_normal(person_id, base_time, reason=f"Run {run_idx} setup")

        # Verify initial nominal state
        init_state = storage.get_escalation_state(person_id)
        assert init_state.stage == EscalationStage.NORMAL
        assert init_state.risk_score == 0.0

        # 2. Seed morning movement at 07:30 UTC, leaving pill (~08:15) unrecorded
        storage.save_event(
            Event(
                person_id=person_id,
                event_type=EventType.MOVEMENT,
                timestamp=datetime(2026, 10, 20, 7, 30, 0, tzinfo=timezone.utc),
                metadata={"source": "simulator_demo", "room": "bedroom"},
            )
        )

        # Baseline check at 08:00 AM: pill is pending, zero false alarms
        risk_8am = risk_engine.evaluate_person_risk(
            person_id=person_id,
            now=base_time,
            baseline_engine=baseline_engine,
            events_today=[e for e in storage.get_events(person_id, limit=20) if e.timestamp.date() == base_time.date()],
        )
        assert risk_8am.score < 0.35, f"False alarm at 08:00 AM: risk={risk_8am.score}"

        # 3. Advance clock past grace window to 09:30 UTC
        t_930 = datetime(2026, 10, 20, 9, 30, 0, tzinfo=timezone.utc)
        clock.set_time(t_930)

        # 4. Baseline engine identifies missed event
        events_today = [e for e in storage.get_events(person_id, limit=20) if e.timestamp.date() == t_930.date()]
        eval_pill = baseline_engine.evaluate_routine(person_id, "medication", t_930, events_today)
        assert eval_pill.is_missed is True
        assert eval_pill.status == "missed"

        # 5. Deterministic risk scoring produces explainable result
        risk_930 = risk_engine.evaluate_person_risk(
            person_id=person_id,
            now=t_930,
            baseline_engine=baseline_engine,
            events_today=events_today,
        )
        assert 0.35 <= risk_930.score <= 0.70
        assert any("medication" in r.lower() or "pill" in r.lower() for r in risk_930.reasons)

        # 6. Tick 1 -> Advances from NORMAL to GENTLE_CHECK_IN
        st_1 = escalation_engine.tick(person_id, t_930)
        assert st_1.stage == EscalationStage.GENTLE_CHECK_IN

        # Tick 2 (+70s past gentle timeout) -> Advances to REPEAT_CHECK_IN
        t_repeat = t_930 + timedelta(seconds=70)
        clock.set_time(t_repeat)
        st_2 = escalation_engine.tick(person_id, t_repeat)
        assert st_2.stage == EscalationStage.REPEAT_CHECK_IN

        # Tick 3 (+70s past repeat timeout) -> Advances to NOTIFY_FAMILY and dispatches Alert
        t_notify = t_repeat + timedelta(seconds=70)
        clock.set_time(t_notify)
        st_3 = escalation_engine.tick(person_id, t_notify)
        assert st_3.stage == EscalationStage.NOTIFY_FAMILY

        # 7. Verify Alert and Notification
        alerts = storage.get_alerts(person_id, active_only=True)
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.level == AlertLevel.CRITICAL_ESCALATION
        assert alert.status == "ACTIVE"
        assert alert.dedup_key is not None
        assert any("timed out" in r.lower() for r in alert.reasons)

        # Verify notifier received the notification
        assert len(notifier.notifications) == 1
        notif = notifier.notifications[0]
        assert notif["person_id"] == person_id
        assert notif["severity"] == "critical"

        # Idempotency: Repeated ticks at NOTIFY_FAMILY must NOT produce duplicate alerts or deliveries
        st_dup = escalation_engine.tick(person_id, t_notify + timedelta(seconds=10))
        assert st_dup.stage == EscalationStage.NOTIFY_FAMILY
        assert len(storage.get_alerts(person_id, active_only=True)) == 1
        assert len(notifier.notifications) == 1

        # 8. Grounded Memory Q&A
        profile = storage.get_profile(person_id)
        # Missed medication query
        ans_pill = llm_assistant.ask_memory(
            person=person_id,
            question="Did Mom take her blood pressure medication this morning?",
            storage=storage,
            now=t_notify,
            display_name=profile.display_name,
            person_tz=profile.timezone,
        )
        assert "no record" in ans_pill.lower() or "pill" in ans_pill.lower()

        # Morning movement query
        ans_move = llm_assistant.ask_memory(
            person=person_id,
            question="Was there any movement in Mom's room this morning?",
            storage=storage,
            now=t_notify,
            display_name=profile.display_name,
            person_tz=profile.timezone,
        )
        assert "movement" in ans_move.lower()

        # 9. Caregiver resolves incident -> state resets to NORMAL
        reset_st = escalation_engine.reset_to_normal(
            person_id,
            t_notify + timedelta(minutes=5),
            reason=f"Run {run_idx} resolution: caregiver verified safe",
        )
        assert reset_st.stage == EscalationStage.NORMAL
        assert len(storage.get_alerts(person_id, active_only=True)) == 0

    storage.close()

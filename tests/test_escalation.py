"""
Unit tests for CareLoop persisted escalation state machine (engine/escalation.py).

Tests every transition:
1. normal -> normal (low risk)
2. normal -> gentle_check_in (risk >= medium)
3. gentle_check_in -> gentle_check_in (before timeout)
4. gentle_check_in -> repeat_check_in (after timeout)
5. repeat_check_in -> repeat_check_in (before timeout)
6. repeat_check_in -> notify_family (after timeout, dispatches Alert)
7. reset to normal upon any new event
8. reset to normal upon person replying "I'm fine"
9. state persistence in DB across stateless engine instances
"""

from datetime import datetime, timezone, timedelta
import os
import tempfile
import pytest

from careloop.clock import SimulatedClock
from careloop.engine.escalation import EscalationEngine
from careloop.engine.risk import RiskAssessment, RiskEngine
from careloop.models import EscalationStage, Event, EventType
from careloop.storage.sqlite_store import SQLiteStorage


@pytest.fixture
def temp_env():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    storage = SQLiteStorage(db_path=path)
    clock = SimulatedClock(datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc))
    # Configure short demo timeouts: gentle=60s, repeat=60s
    engine = EscalationEngine(
        storage=storage,
        gentle_timeout_seconds=60.0,
        repeat_timeout_seconds=60.0,
    )
    yield storage, clock, engine
    storage.close()
    if os.path.exists(path):
        os.remove(path)


def test_transition_normal_to_normal_low_risk(temp_env):
    storage, clock, engine = temp_env
    low_risk = RiskAssessment(score=0.0, level="low", reasons=["Nominal"])

    state = engine.tick("eleanor", clock.now(), forced_risk=low_risk)
    assert state.stage == EscalationStage.NORMAL


def test_transition_normal_to_gentle_check_in(temp_env):
    storage, clock, engine = temp_env
    # Medium risk: medication missed (0.4)
    med_risk = RiskAssessment(
        score=0.4,
        level="medium",
        reasons=["Medication missed past baseline grace window"],
    )

    state = engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    assert state.stage == EscalationStage.GENTLE_CHECK_IN
    assert state.risk_score == 0.4
    assert len(state.reasons) >= 1


def test_transition_gentle_to_repeat_check_in_on_timeout(temp_env):
    storage, clock, engine = temp_env
    med_risk = RiskAssessment(score=0.4, level="medium", reasons=["Medication missed"])

    # 1. Trigger transition into gentle_check_in at t = 0s
    state_gentle = engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    assert state_gentle.stage == EscalationStage.GENTLE_CHECK_IN

    # 2. Advance 30 seconds (before 60s timeout): should stay in gentle_check_in
    clock.advance(30)
    state_stay = engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    assert state_stay.stage == EscalationStage.GENTLE_CHECK_IN

    # 3. Advance past 60s timeout (+40s, total 70s): should transition to repeat_check_in
    clock.advance(40)
    state_repeat = engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    assert state_repeat.stage == EscalationStage.REPEAT_CHECK_IN


def test_transition_repeat_to_notify_family_on_timeout(temp_env):
    storage, clock, engine = temp_env
    med_risk = RiskAssessment(score=0.4, level="medium", reasons=["Medication missed"])

    # Start at normal, advance through gentle into repeat
    engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    clock.advance(65)
    state_repeat = engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    assert state_repeat.stage == EscalationStage.REPEAT_CHECK_IN

    # Stay in repeat before timeout (advance 30s)
    clock.advance(30)
    state_repeat_stay = engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    assert state_repeat_stay.stage == EscalationStage.REPEAT_CHECK_IN

    # Advance past repeat timeout (advance 40s, total 70s) -> notify_family!
    clock.advance(40)
    state_notify = engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    assert state_notify.stage == EscalationStage.NOTIFY_FAMILY

    # Verify deterministic alert was persisted to storage
    alerts = storage.get_alerts("eleanor", active_only=True)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.title.startswith("Elder Care Alert")
    assert any("timed out" in r.lower() for r in alert.reasons)
    assert alert.status == "ACTIVE"


def test_reset_to_normal_on_new_event(temp_env):
    storage, clock, engine = temp_env
    med_risk = RiskAssessment(score=0.4, level="medium", reasons=["Medication missed"])

    # Push to repeat_check_in
    engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    clock.advance(70)
    engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    assert storage.get_escalation_state("eleanor").stage == EscalationStage.REPEAT_CHECK_IN

    # Elder logs a movement or meal event -> resets to NORMAL
    clock.advance(10)
    reset_state = engine.reset_to_normal(
        "eleanor",
        now=clock.now(),
        reason="Observed kitchen movement event",
    )
    assert reset_state.stage == EscalationStage.NORMAL
    assert reset_state.risk_score == 0.0

    # Persisted state is also normal
    persisted = storage.get_escalation_state("eleanor")
    assert persisted.stage == EscalationStage.NORMAL


def test_reset_to_normal_on_person_replying_im_fine(temp_env):
    storage, clock, engine = temp_env
    med_risk = RiskAssessment(score=0.4, level="medium", reasons=["Medication missed"])

    # Push to gentle_check_in
    engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    assert storage.get_escalation_state("eleanor").stage == EscalationStage.GENTLE_CHECK_IN

    # Alexa checks in: "Eleanor, did you take your morning pills?"
    # Eleanor responds: "I'm fine, just had breakfast and took them"
    clock.advance(15)
    resp_state = engine.handle_voice_response(
        "eleanor",
        "I'm fine, just had breakfast and took them",
        clock.now(),
    )
    assert resp_state.stage == EscalationStage.NORMAL

    # Verify persisted in DB
    persisted = storage.get_escalation_state("eleanor")
    assert persisted.stage == EscalationStage.NORMAL


def test_stateless_server_persistence(temp_env):
    """
    Simulates separate stateless server processes reading and writing the state machine.
    """
    storage, clock, engine1 = temp_env
    med_risk = RiskAssessment(score=0.4, level="medium", reasons=["Medication missed"])

    # Process 1 puts state into GENTLE_CHECK_IN
    engine1.tick("eleanor", clock.now(), forced_risk=med_risk)
    del engine1  # Process 1 dies

    # Time advances 75 seconds
    clock.advance(75)

    # Process 2 starts up fresh with only the DB connection
    engine2 = EscalationEngine(
        storage=storage,
        gentle_timeout_seconds=60.0,
        repeat_timeout_seconds=60.0,
    )
    state2 = engine2.tick("eleanor", clock.now(), forced_risk=med_risk)

    # Must accurately transition to REPEAT_CHECK_IN based on persisted DB state!
    assert state2.stage == EscalationStage.REPEAT_CHECK_IN


def test_repeated_ticks_at_same_timestamp_are_idempotent(temp_env):
    """
    Verify:
    Calling tick() multiple times with the exact same timestamp is idempotent:
    1. Does NOT advance stages prematurely.
    2. Does NOT trigger multiple timeouts in 0 seconds.
    3. Does NOT dispatch duplicate family alerts.
    """
    storage, clock, engine = temp_env
    med_risk = RiskAssessment(score=0.4, level="medium", reasons=["Medication missed"])

    # 1. First tick at t=0s -> GENTLE_CHECK_IN
    t0 = clock.now()
    s1 = engine.tick("eleanor", t0, forced_risk=med_risk)
    assert s1.stage == EscalationStage.GENTLE_CHECK_IN

    # Repeat tick 5 times at t0 -> Must remain in GENTLE_CHECK_IN!
    for _ in range(5):
        s_repeat = engine.tick("eleanor", t0, forced_risk=med_risk)
        assert s_repeat.stage == EscalationStage.GENTLE_CHECK_IN

    # 2. Advance clock past 60s gentle timeout (+65s) -> transitions to REPEAT_CHECK_IN
    clock.advance(65)
    t1 = clock.now()
    s_repeat_stage = engine.tick("eleanor", t1, forced_risk=med_risk)
    assert s_repeat_stage.stage == EscalationStage.REPEAT_CHECK_IN

    # Repeat tick 5 times at t1 -> Must remain in REPEAT_CHECK_IN!
    for _ in range(5):
        s_repeat2 = engine.tick("eleanor", t1, forced_risk=med_risk)
        assert s_repeat2.stage == EscalationStage.REPEAT_CHECK_IN

    # 3. Advance clock past 60s repeat timeout (+65s) -> transitions to NOTIFY_FAMILY
    clock.advance(65)
    t2 = clock.now()
    s_notify = engine.tick("eleanor", t2, forced_risk=med_risk)
    assert s_notify.stage == EscalationStage.NOTIFY_FAMILY

    # Repeat tick 5 times at t2 -> Must remain in NOTIFY_FAMILY and NOT duplicate alerts
    for _ in range(5):
        s_notify_repeat = engine.tick("eleanor", t2, forced_risk=med_risk)
        assert s_notify_repeat.stage == EscalationStage.NOTIFY_FAMILY

    # Verify that only ONE Alert was persisted
    alerts = storage.get_alerts("eleanor", active_only=True)
    assert len(alerts) == 1, f"Expected exactly 1 alert, found {len(alerts)}"


def test_naive_tick_timestamp_rejected(temp_env):
    storage, clock, engine = temp_env
    naive_dt = datetime(2026, 10, 20, 8, 0, 0)  # No tzinfo

    with pytest.raises(ValueError) as excinfo:
        engine.tick("eleanor", naive_dt)
    assert "timezone-aware" in str(excinfo.value)

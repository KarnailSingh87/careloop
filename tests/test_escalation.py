"""
Unit tests for CareLoop persisted escalation state machine (engine/escalation.py).

Verifies the complete state machine contract:
1. normal -> normal (low risk)
2. normal -> gentle_check_in (risk >= medium)
3. gentle_check_in timeout boundary: stays at t < timeout, transitions at t >= timeout
4. repeat_check_in timeout boundary: stays at t < timeout, transitions at t >= timeout
5. notify_family creates deterministic Alert with evidence reasons and decision_id
6. Repeated ticks on any stage are idempotent (0 duplicate alerts, 0 duplicate notifications)
7. Reset to normal upon qualifying routine event (records event reference, resolves active alerts)
8. Reset to normal upon voice confirmation ("I'm fine", "okay", etc.)
9. Server restart / stateless persistence across separate engine instances
10. Separation of notification decision vs delivery
11. Notification delivery failure recording (failure status, delivery_error, retry_count)
12. Notification retry delivering failed alert without duplicating successful deliveries
13. Stale background worker prevention via optimistic concurrency (StaleStateError)
14. Stale background worker cannot overwrite elder confirm_ok / event reset
15. Zero events never infers safety (missed routine windows escalate risk)
16. Timezone-awareness requirement (naive timestamps rejected)
"""

from datetime import datetime, timezone, timedelta
import os
import tempfile
import uuid
import pytest

from careloop.clock import SimulatedClock
from careloop.engine.baseline import BaselineEngine
from careloop.engine.escalation import EscalationEngine
from careloop.engine.risk import RiskAssessment, RiskEngine
from careloop.models import (
    Alert,
    AlertLevel,
    EscalationStage,
    Event,
    EventType,
    PersonProfile,
    EmergencyContact,
    RoutineRule,
    RoutineType,
)
from careloop.notifier import NotifierBase
from careloop.storage.base import StaleStateError
from careloop.storage.sqlite_store import SQLiteStorage


class MockFailingNotifier(NotifierBase):
    """Mock notifier to simulate delivery failures and subsequent recovery."""

    def __init__(self, fail: bool = True):
        self.fail = fail
        self.call_count = 0
        self.delivered_alerts = []

    def send_notification(
        self,
        person_id: str,
        severity: str,
        message: str,
        reasons=None,
        contacts=None,
        dedup_key=None,
        **kwargs,
    ) -> bool:
        self.call_count += 1
        if self.fail:
            return False
        self.delivered_alerts.append((person_id, severity, message))
        return True


@pytest.fixture
def temp_env():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    storage = SQLiteStorage(db_path=path)
    clock = SimulatedClock(datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc))
    # Configure short test timeouts: gentle=60s, repeat=60s
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
    assert state.notification_state == "none"


def test_transition_normal_to_gentle_check_in(temp_env):
    storage, clock, engine = temp_env
    med_risk = RiskAssessment(
        score=0.4,
        level="medium",
        reasons=["Medication missed past baseline grace window"],
    )

    state = engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    assert state.stage == EscalationStage.GENTLE_CHECK_IN
    assert state.risk_score == 0.4
    assert len(state.reasons) >= 1
    assert state.notification_state == "none"


def test_timeout_boundaries_exact(temp_env):
    """Verify exact boundary behavior for gentle and repeat check-in timeouts."""
    storage, clock, engine = temp_env
    med_risk = RiskAssessment(score=0.4, level="medium", reasons=["Medication missed"])

    # t0: enters gentle_check_in
    t0 = clock.now()
    s0 = engine.tick("eleanor", t0, forced_risk=med_risk)
    assert s0.stage == EscalationStage.GENTLE_CHECK_IN

    # t0 + 59.9s (strictly before 60s timeout): MUST stay in gentle_check_in
    clock.advance(59.9)
    s_sub = engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    assert s_sub.stage == EscalationStage.GENTLE_CHECK_IN

    # t0 + 60.0s (exact boundary): MUST transition to repeat_check_in
    clock.advance(0.1)
    s_rep = engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    assert s_rep.stage == EscalationStage.REPEAT_CHECK_IN

    # In repeat_check_in at t_rep: advance 59.9s: MUST stay in repeat_check_in
    clock.advance(59.9)
    s_rep_stay = engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    assert s_rep_stay.stage == EscalationStage.REPEAT_CHECK_IN

    # Advance 0.1s (total 60.0s): MUST transition to notify_family
    clock.advance(0.1)
    s_not = engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    assert s_not.stage == EscalationStage.NOTIFY_FAMILY


def test_notification_decision_separated_from_delivery(temp_env):
    """
    Verify decision to notify creates an Alert with pending status and traceable identifiers
    prior to delivery, and delivery transitions status to 'delivered'.
    """
    storage, clock, engine = temp_env
    mock_notifier = MockFailingNotifier(fail=False)
    engine.notifier = mock_notifier

    med_risk = RiskAssessment(
        score=0.5,
        level="high",
        reasons=["Missed morning medication", "Zero movement detected"],
    )

    # Step through gentle and repeat check-in into notify_family
    engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    clock.advance(60.0)
    engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    clock.advance(60.0)
    state = engine.tick("eleanor", clock.now(), forced_risk=med_risk)

    assert state.stage == EscalationStage.NOTIFY_FAMILY
    assert state.notification_state == "delivered"
    assert state.notification_id is not None

    # Check persisted alert
    alerts = storage.get_alerts("eleanor", active_only=True)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.alert_id == state.notification_id
    assert alert.notification_status == "delivered"
    assert alert.delivered_at is not None
    assert alert.delivery_error is None
    assert alert.retry_count == 0
    assert "decision_id" in alert.metadata
    assert alert.level == AlertLevel.CRITICAL_ESCALATION
    assert len(alert.reasons) >= 3


def test_notification_delivery_failure_and_retry(temp_env):
    """
    Verify delivery failure:
    1. Records notification_status='failed', delivery_error, and increments retry_count.
    2. Keeps alert in storage and does not duplicate alerts on repeated ticks.
    3. retry_failed_notifications delivers the existing alert without duplication.
    """
    storage, clock, engine = temp_env
    mock_notifier = MockFailingNotifier(fail=True)  # Simulates SMS delivery failure
    engine.notifier = mock_notifier

    med_risk = RiskAssessment(score=0.5, level="high", reasons=["Missed medication"])

    # Push to notify_family
    engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    clock.advance(60.0)
    engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    clock.advance(60.0)
    state = engine.tick("eleanor", clock.now(), forced_risk=med_risk)

    # Decision made, but delivery failed!
    assert state.stage == EscalationStage.NOTIFY_FAMILY
    assert state.notification_state == "failed"

    alerts = storage.get_alerts("eleanor", active_only=True)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.notification_status == "failed"
    assert alert.retry_count == 1
    assert alert.delivery_error is not None
    assert alert.delivered_at is None

    # Next tick: retries delivery of the SAME alert without creating a duplicate
    clock.advance(10.0)
    state2 = engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    assert state2.notification_state == "failed"
    alerts2 = storage.get_alerts("eleanor", active_only=True)
    assert len(alerts2) == 1  # No duplicate alert created!
    assert alerts2[0].retry_count == 2

    # Now recover the notifier
    mock_notifier.fail = False
    delivered = engine.retry_failed_notifications("eleanor", clock.now())
    assert delivered == 1

    # Verify alert is now delivered
    alerts3 = storage.get_alerts("eleanor", active_only=True)
    assert len(alerts3) == 1
    assert alerts3[0].notification_status == "delivered"
    assert alerts3[0].delivered_at is not None

    # Verify state notification_state is now delivered
    state_after = storage.get_escalation_state("eleanor")
    assert state_after.notification_state == "delivered"

    # Subsequent tick must NOT re-deliver (idempotent)
    call_count_before = mock_notifier.call_count
    clock.advance(15.0)
    engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    assert mock_notifier.call_count == call_count_before


def test_concurrent_tick_optimistic_concurrency_conflict(temp_env):
    """
    Verify that if a background worker attempts to write with an outdated state version,
    StaleStateError is raised and the newer state is preserved.
    """
    storage, clock, engine = temp_env
    med_risk = RiskAssessment(score=0.4, level="medium", reasons=["Missed routine"])

    # Worker A and Worker B both read initial state (version 1)
    state_a = engine.get_or_create_state("eleanor", clock.now())
    state_b = storage.get_escalation_state("eleanor")
    assert state_a.version == 1
    assert state_b.version == 1

    # Worker A executes tick, advancing state to GENTLE_CHECK_IN (increments to version 2)
    engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    persisted = storage.get_escalation_state("eleanor")
    assert persisted.stage == EscalationStage.GENTLE_CHECK_IN
    assert persisted.version == 2

    # Worker B (stale worker with version 1) tries to save an old state
    state_b.reasons = ["Stale reasons"]
    with pytest.raises(StaleStateError) as excinfo:
        storage.save_escalation_state(state_b, check_version=True)
    assert "version" in str(excinfo.value).lower() or "stale" in str(excinfo.value).lower()

    # The persisted stage remains GENTLE_CHECK_IN (Worker B did not overwrite)
    final_state = storage.get_escalation_state("eleanor")
    assert final_state.stage == EscalationStage.GENTLE_CHECK_IN
    assert final_state.version == 2


def test_stale_worker_cannot_overwrite_confirm_ok_or_event_reset(temp_env):
    """
    Critical safety test:
    If a background worker prepares an escalation update, but the elder confirms OK
    in the meantime, the stale worker's write MUST be rejected.
    """
    storage, clock, engine = temp_env
    med_risk = RiskAssessment(score=0.4, level="medium", reasons=["Missed routine"])

    # 1. State reaches REPEAT_CHECK_IN
    engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    clock.advance(65)
    engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    stale_state = storage.get_escalation_state("eleanor")
    assert stale_state.stage == EscalationStage.REPEAT_CHECK_IN

    # 2. Elder confirms OK: "I'm fine, Alexa"
    clock.advance(5)
    engine.handle_voice_response("eleanor", "I'm fine, Alexa", clock.now())
    persisted = storage.get_escalation_state("eleanor")
    assert persisted.stage == EscalationStage.NORMAL

    # 3. Stale worker attempts to save REPEAT_CHECK_IN or NOTIFY_FAMILY with stale version
    with pytest.raises(StaleStateError):
        storage.save_escalation_state(stale_state, check_version=True)

    # Confirm safe status was NOT overwritten
    persisted_after = storage.get_escalation_state("eleanor")
    assert persisted_after.stage == EscalationStage.NORMAL


def test_reset_on_qualifying_event_and_confirm_ok_resolves_active_alerts(temp_env):
    """
    Verify that resetting escalation to NORMAL upon confirm_ok or a new routine event
    automatically resolves active alerts in storage.
    """
    storage, clock, engine = temp_env
    med_risk = RiskAssessment(score=0.5, level="high", reasons=["Medication missed"])

    # Escalate to NOTIFY_FAMILY to create an active alert
    engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    clock.advance(60)
    engine.tick("eleanor", clock.now(), forced_risk=med_risk)
    clock.advance(60)
    engine.tick("eleanor", clock.now(), forced_risk=med_risk)

    alerts_before = storage.get_alerts("eleanor", active_only=True)
    assert len(alerts_before) == 1
    assert alerts_before[0].status == "ACTIVE"

    # Elder logs a routine pill event
    clock.advance(30)
    new_event = Event(
        person_id="eleanor",
        event_type=EventType.PILL,
        timestamp=clock.now(),
        metadata={"pill": "blood_pressure"},
    )
    storage.save_event(new_event)
    reset_state = engine.reset_on_event(new_event)

    assert reset_state.stage == EscalationStage.NORMAL
    assert reset_state.notification_state == "none"
    assert new_event.event_id in reset_state.event_references

    # Verify active alert was marked RESOLVED
    active_alerts_after = storage.get_alerts("eleanor", active_only=True)
    assert len(active_alerts_after) == 0

    all_alerts = storage.get_alerts("eleanor", active_only=False)
    assert len(all_alerts) == 1
    assert all_alerts[0].status == "RESOLVED"
    assert "resolved_at" in all_alerts[0].metadata


def test_stateless_server_persistence(temp_env):
    """
    Simulates server crash and restart across separate engine instances.
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
    Verify calling tick() multiple times with the exact same timestamp is idempotent:
    1. Does NOT advance stages prematurely.
    2. Does NOT trigger multiple timeouts in 0 seconds.
    3. Does NOT dispatch duplicate family alerts.
    """
    storage, clock, engine = temp_env
    med_risk = RiskAssessment(score=0.4, level="medium", reasons=["Medication missed"])

    t0 = clock.now()
    s1 = engine.tick("eleanor", t0, forced_risk=med_risk)
    assert s1.stage == EscalationStage.GENTLE_CHECK_IN

    # Repeat tick 5 times at t0 -> Must remain in GENTLE_CHECK_IN!
    for _ in range(5):
        s_repeat = engine.tick("eleanor", t0, forced_risk=med_risk)
        assert s_repeat.stage == EscalationStage.GENTLE_CHECK_IN

    # Advance clock past 60s gentle timeout -> transitions to REPEAT_CHECK_IN
    clock.advance(65)
    t1 = clock.now()
    s_repeat_stage = engine.tick("eleanor", t1, forced_risk=med_risk)
    assert s_repeat_stage.stage == EscalationStage.REPEAT_CHECK_IN

    # Repeat tick 5 times at t1 -> Must remain in REPEAT_CHECK_IN!
    for _ in range(5):
        s_repeat2 = engine.tick("eleanor", t1, forced_risk=med_risk)
        assert s_repeat2.stage == EscalationStage.REPEAT_CHECK_IN

    # Advance clock past 60s repeat timeout -> transitions to NOTIFY_FAMILY
    clock.advance(65)
    t2 = clock.now()
    s_notify = engine.tick("eleanor", t2, forced_risk=med_risk)
    assert s_notify.stage == EscalationStage.NOTIFY_FAMILY

    # Repeat tick 5 times at t2 -> Must remain in NOTIFY_FAMILY and NOT duplicate alerts
    for _ in range(5):
        s_notify_repeat = engine.tick("eleanor", t2, forced_risk=med_risk)
        assert s_notify_repeat.stage == EscalationStage.NOTIFY_FAMILY

    alerts = storage.get_alerts("eleanor", active_only=True)
    assert len(alerts) == 1, f"Expected exactly 1 alert, found {len(alerts)}"


def test_zero_events_never_infers_safety(temp_env):
    """
    Safety property:
    The absence of events past morning waking hours (10:00 AM) MUST NOT be inferred as safety.
    The system identifies daytime inactivity, elevates risk score, and enters GENTLE_CHECK_IN.
    """
    storage, clock, engine = temp_env

    # Set clock to 10:00 AM UTC (past 09:00 morning wake threshold) with ZERO events recorded
    clock.set_time(datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc))

    # Evaluate tick
    state = engine.tick("eleanor", clock.now())

    # State machine must escalate to gentle check-in because routine was missed!
    assert state.stage == EscalationStage.GENTLE_CHECK_IN
    assert state.risk_score >= 0.3
    assert any("inactivity" in r.lower() or "no movement" in r.lower() for r in state.reasons)


def test_naive_tick_timestamp_rejected(temp_env):
    storage, clock, engine = temp_env
    naive_dt = datetime(2026, 10, 20, 8, 0, 0)  # No tzinfo

    with pytest.raises(ValueError) as excinfo:
        engine.tick("eleanor", naive_dt)
    assert "timezone-aware" in str(excinfo.value)

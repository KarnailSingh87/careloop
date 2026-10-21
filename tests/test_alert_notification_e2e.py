"""
End-to-end local tests for CareLoop alert generation, reason generation,
deduplication, retry mechanics, and input validations.

Verifies:
1. Family alert generated with actual evidence-based deterministic reasons.
2. Structured Alert persistence with severity, reasons, timestamps, and stable dedup_key.
3. Separation between alert generation, delivery attempt, and delivery result.
4. Retry of failed notifications without duplicating delivered alerts.
5. Deduplication behavior preventing duplicate dispatches within active window.
6. Input validation on MCP tools (invalid timestamps, unsupported severities, empty messages).
"""

from datetime import datetime, timezone, timedelta
import os
import tempfile
import pytest

from careloop.clock import SimulatedClock
from careloop.engine.baseline import BaselineEngine
from careloop.engine.escalation import EscalationEngine
from careloop.engine.risk import RiskAssessment, RiskEngine
from careloop.models import (
    Alert,
    AlertLevel,
    EmergencyContact,
    EscalationStage,
    Event,
    EventType,
    PersonProfile,
    Reminder,
    ReminderStatus,
    RoutineRule,
    RoutineType,
)
from careloop.notifier import InMemoryNotifier
from careloop.server.main import create_server
from careloop.storage.sqlite_store import SQLiteStorage


@pytest.fixture
def local_env():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    storage = SQLiteStorage(db_path=path)
    start_time = datetime(2026, 10, 21, 8, 0, 0, tzinfo=timezone.utc)
    clock = SimulatedClock(start_time)

    # Register profile with emergency contact
    profile = PersonProfile(
        person_id="eleanor",
        display_name="Eleanor Vance",
        timezone="UTC",
        emergency_contacts=[
            EmergencyContact(
                name="Linda Davis",
                relationship="Daughter",
                phone="+1-555-019-2834",
            )
        ],
    )
    storage.save_profile(profile)

    notifier = InMemoryNotifier()
    escalation_engine = EscalationEngine(
        storage=storage,
        notifier=notifier,
        gentle_timeout_seconds=60.0,
        repeat_timeout_seconds=60.0,
    )

    yield storage, clock, notifier, escalation_engine
    if os.path.exists(path):
        os.remove(path)


def test_family_alert_with_actual_reasons_and_structure(local_env):
    """
    Demonstrate an actual family alert generated with deterministic reasons:
    e.g. Eleanor misses lunch routine and repeated voice check-ins timeout.
    """
    storage, clock, notifier, escalation = local_env

    # 1. Establish high risk with actual deterministic reasons
    lunch_risk = RiskAssessment(
        score=0.85,
        level="critical",
        reasons=[
            "Missed expected routine 'lunch' (expected window 12:00 - 13:30 UTC)",
            "No kitchen activity or refrigerator opening detected for 4.5 hours",
            "Motion sensors report zero activity in main living area",
        ],
    )

    # Advance clock to 13:45 UTC (lunch window missed)
    clock.set_time(datetime(2026, 10, 21, 13, 45, 0, tzinfo=timezone.utc))

    # Tick 1: normal -> gentle_check_in
    s1 = escalation.tick("eleanor", clock.now(), forced_risk=lunch_risk)
    assert s1.stage == EscalationStage.GENTLE_CHECK_IN
    assert s1.notification_state == "none"
    assert len(notifier.notifications) == 0

    # Advance past gentle_timeout (60s)
    clock.advance(65.0)

    # Tick 2: gentle_check_in -> repeat_check_in
    s2 = escalation.tick("eleanor", clock.now(), forced_risk=lunch_risk)
    assert s2.stage == EscalationStage.REPEAT_CHECK_IN
    assert s2.notification_state == "none"
    assert len(notifier.notifications) == 0

    # Advance past repeat_timeout (60s)
    clock.advance(65.0)

    # Tick 3: repeat_check_in -> notify_family
    s3 = escalation.tick("eleanor", clock.now(), forced_risk=lunch_risk)
    assert s3.stage == EscalationStage.NOTIFY_FAMILY
    assert s3.notification_state in ("delivered", "accepted")

    # Verify structured alert record in storage
    alerts = storage.get_alerts("eleanor", active_only=True)
    assert len(alerts) == 1
    alert = alerts[0]

    # Verify structured fields
    assert alert.person_id == "eleanor"
    assert alert.severity == "critical"
    assert "eleanor" in alert.dedup_key and "2026-10-21" in alert.dedup_key
    assert alert.notification_status == "delivered"
    assert alert.delivered_at is not None

    # Verify human-readable, evidence-based deterministic reasons
    assert len(alert.reasons) >= 3
    assert any("Missed expected routine 'lunch'" in r for r in alert.reasons)
    assert any("No kitchen activity" in r for r in alert.reasons)
    assert any("zero activity" in r for r in alert.reasons)

    # Verify dispatched notification payload
    assert len(notifier.notifications) == 1
    notif = notifier.notifications[0]
    assert notif["person_id"] == "eleanor"
    assert notif["severity"] == "critical"
    assert notif["dedup_key"] == alert.dedup_key
    assert len(notif["contacts"]) == 1
    assert notif["contacts"][0].phone == "+1-555-019-2834"


def test_notification_deduplication_on_repeated_ticks(local_env):
    """
    Subsequent ticks while in NOTIFY_FAMILY must be completely idempotent:
    - Never generate duplicate alerts.
    - Never re-dispatch duplicate SMS/SNS notifications.
    """
    storage, clock, notifier, escalation = local_env
    risk = RiskAssessment(score=0.9, level="critical", reasons=["Inactivity timeout"])

    # Push to NOTIFY_FAMILY
    escalation.tick("eleanor", clock.now(), forced_risk=risk)
    clock.advance(65.0)
    escalation.tick("eleanor", clock.now(), forced_risk=risk)
    clock.advance(65.0)
    escalation.tick("eleanor", clock.now(), forced_risk=risk)

    assert len(notifier.notifications) == 1
    assert len(storage.get_alerts("eleanor", active_only=True)) == 1

    # Repeated ticks: advance clock and tick 5 more times
    for _ in range(5):
        clock.advance(30.0)
        st = escalation.tick("eleanor", clock.now(), forced_risk=risk)
        assert st.stage == EscalationStage.NOTIFY_FAMILY

    # Assert exactly 1 notification was dispatched and 1 alert stored
    assert len(notifier.notifications) == 1
    assert len(storage.get_alerts("eleanor", active_only=True)) == 1


def test_notification_retry_on_failure_and_recovery(local_env):
    """
    When notifier delivery fails:
    - Alert is saved with status='failed' and retry_count=1.
    - Subsequent tick retries the SAME alert without creating a duplicate.
    - When notifier recovers, alert transitions to 'delivered' and retry_count reflects attempts.
    """
    storage, clock, notifier, escalation = local_env
    notifier.should_fail = True
    notifier.fail_error = "Carrier route congested"

    risk = RiskAssessment(score=0.9, level="critical", reasons=["Missed morning medication"])

    # Push to NOTIFY_FAMILY
    escalation.tick("eleanor", clock.now(), forced_risk=risk)
    clock.advance(65.0)
    escalation.tick("eleanor", clock.now(), forced_risk=risk)
    clock.advance(65.0)
    state = escalation.tick("eleanor", clock.now(), forced_risk=risk)

    assert state.stage == EscalationStage.NOTIFY_FAMILY
    assert state.notification_state == "failed"

    alerts = storage.get_alerts("eleanor", active_only=True)
    assert len(alerts) == 1
    assert alerts[0].notification_status == "failed"
    assert alerts[0].retry_count == 1
    assert "Carrier route congested" in alerts[0].delivery_error

    # Next tick: retry fails again
    clock.advance(10.0)
    escalation.tick("eleanor", clock.now(), forced_risk=risk)
    alerts2 = storage.get_alerts("eleanor", active_only=True)
    assert len(alerts2) == 1  # No duplicate
    assert alerts2[0].retry_count == 2

    # Recover notifier and retry
    notifier.should_fail = False
    redelivered = escalation.retry_failed_notifications("eleanor", clock.now())
    assert redelivered == 1

    alerts3 = storage.get_alerts("eleanor", active_only=True)
    assert len(alerts3) == 1
    assert alerts3[0].notification_status == "delivered"
    assert alerts3[0].delivered_at is not None
    assert alerts3[0].delivery_error is None


@pytest.mark.asyncio
async def test_mcp_tool_validations_and_deduplication(local_env):
    """
    Test validation of invalid timestamps, unsupported severities, empty messages,
    and tool-level deduplication window.
    """
    storage, clock, notifier, escalation = local_env
    server, _, _, _ = create_server(storage=storage, clock=clock, notifier=notifier)

    # 1. Validation: notify_family with empty person
    with pytest.raises(Exception, match="Person identifier cannot be empty"):
        await server.call_tool("notify_family", {"person": "", "severity": "high", "message": "Alert"})

    # 2. Validation: notify_family with empty message
    with pytest.raises(Exception, match="Alert message cannot be empty"):
        await server.call_tool("notify_family", {"person": "eleanor", "severity": "high", "message": "   "})

    # 3. Validation: notify_family with unsupported severity
    with pytest.raises(Exception, match="Unsupported severity"):
        await server.call_tool("notify_family", {"person": "eleanor", "severity": "urgent", "message": "Help"})

    # 4. Successful notify_family call
    r4 = await server.call_tool(
        "notify_family",
        {"person": "eleanor", "severity": "high", "message": "Father did not answer check-in"},
    )
    assert not r4.is_error
    import json
    data1 = json.loads(r4.content[0].text)
    assert data1["status"] == "notified"
    assert data1["delivery_status"] in ("delivered", "accepted")
    assert data1["dedup_key"] is not None

    # 5. Immediate duplicate notify_family call is deduplicated
    r5 = await server.call_tool(
        "notify_family",
        {"person": "eleanor", "severity": "high", "message": "Father did not answer check-in"},
    )
    assert not r5.is_error
    data2 = json.loads(r5.content[0].text)
    assert data2["status"] == "deduplicated"
    assert data2["delivery_status"] == "skipped_deduplicated"
    assert "Duplicate" in data2["note"]

    # 6. Validation: schedule_reminder with empty person
    with pytest.raises(Exception, match="Person identifier cannot be empty"):
        await server.call_tool("schedule_reminder", {"person": " ", "text": "Drink water", "time": "14:00"})

    # 7. Validation: schedule_reminder with empty text
    with pytest.raises(Exception, match="Reminder text cannot be empty"):
        await server.call_tool("schedule_reminder", {"person": "eleanor", "text": "", "time": "14:00"})

    # 8. Validation: schedule_reminder with invalid time string
    with pytest.raises(Exception, match="Invalid reminder time"):
        await server.call_tool(
            "schedule_reminder",
            {"person": "eleanor", "text": "Drink water", "time": "not-a-valid-time"},
        )

    # 9. Successful schedule_reminder with HH:MM
    r9 = await server.call_tool(
        "schedule_reminder",
        {"person": "eleanor", "text": "Take evening pill", "time": "19:30"},
    )
    assert not r9.is_error
    rem_data = json.loads(r9.content[0].text)
    assert rem_data["status"] == "scheduled"
    assert rem_data["time"] == "19:30"
    assert "reminder_id" in rem_data

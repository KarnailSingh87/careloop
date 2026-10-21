"""
Unit tests for CareLoop Reminder Scheduler and Lifecycle Manager (careloop/reminders.py).
"""

from datetime import datetime, timezone
import os
import tempfile
import pytest

from careloop.clock import SimulatedClock
from careloop.models import PersonProfile, Reminder, ReminderStatus
from careloop.reminders import (
    ALEXA_REMINDER_DELIVERY_REQUIREMENTS,
    AlexaSkillRemindersBridge,
    ConsoleReminderDeliveryBridge,
    ReminderDeliveryBridge,
    ReminderScheduler,
    is_reminder_due,
)
from careloop.storage.sqlite_store import SQLiteStorage


@pytest.fixture
def temp_storage():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    storage = SQLiteStorage(db_path=path)
    # Seed profile
    storage.save_profile(
        PersonProfile(
            person_id="eleanor",
            display_name="Eleanor Vance",
            timezone="UTC",
        )
    )
    yield storage
    if os.path.exists(path):
        os.remove(path)


def test_is_reminder_due_hh_mm():
    created = datetime(2026, 10, 21, 10, 0, 0, tzinfo=timezone.utc)
    reminder = Reminder(
        person_id="eleanor",
        text="Take heart medication",
        scheduled_time="14:30",
        created_at=created,
    )

    # 1. Before scheduled time -> not due
    now_before = datetime(2026, 10, 21, 14, 29, 0, tzinfo=timezone.utc)
    assert is_reminder_due(reminder, now_before, "UTC") is False

    # 2. At scheduled time -> due
    now_at = datetime(2026, 10, 21, 14, 30, 0, tzinfo=timezone.utc)
    assert is_reminder_due(reminder, now_at, "UTC") is True

    # 3. After scheduled time -> due
    now_after = datetime(2026, 10, 21, 15, 0, 0, tzinfo=timezone.utc)
    assert is_reminder_due(reminder, now_after, "UTC") is True

    # 4. Completed reminder -> not due
    reminder.status = ReminderStatus.COMPLETED
    assert is_reminder_due(reminder, now_after, "UTC") is False


def test_is_reminder_due_iso_format():
    reminder = Reminder(
        person_id="eleanor",
        text="Drink glass of water",
        scheduled_time="2026-10-21T16:00:00+00:00",
        created_at=datetime(2026, 10, 21, 9, 0, 0, tzinfo=timezone.utc),
    )

    before = datetime(2026, 10, 21, 15, 59, 59, tzinfo=timezone.utc)
    assert is_reminder_due(reminder, before) is False

    after = datetime(2026, 10, 21, 16, 0, 1, tzinfo=timezone.utc)
    assert is_reminder_due(reminder, after) is True


def test_is_reminder_due_rejects_naive_timestamp():
    reminder = Reminder(
        person_id="eleanor",
        text="Test",
        scheduled_time="12:00",
    )
    naive_dt = datetime(2026, 10, 21, 12, 0, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        is_reminder_due(reminder, naive_dt)


def test_reminder_scheduler_lifecycle(temp_storage):
    clock = SimulatedClock(datetime(2026, 10, 21, 8, 0, 0, tzinfo=timezone.utc))
    delivered_msgs = []
    bridge = ConsoleReminderDeliveryBridge(output_fn=delivered_msgs.append)
    scheduler = ReminderScheduler(storage=temp_storage, clock=clock, delivery_bridge=bridge)

    # 1. Schedule two reminders: one at 10:00, one at 14:00
    r1 = Reminder(
        person_id="eleanor",
        text="Morning stretches",
        scheduled_time="10:00",
        created_at=clock.now(),
    )
    r2 = Reminder(
        person_id="eleanor",
        text="Afternoon medication",
        scheduled_time="14:00",
        created_at=clock.now(),
    )
    temp_storage.save_reminder(r1)
    temp_storage.save_reminder(r2)

    # Check at 09:00: neither is due
    clock.advance(3600.0)  # 09:00
    processed = scheduler.process_due_reminders("eleanor")
    assert len(processed) == 0
    assert len(delivered_msgs) == 0

    # Advance to 10:05: r1 is due and processed
    clock.advance(3900.0)  # 10:05
    processed = scheduler.process_due_reminders("eleanor")
    assert len(processed) == 1
    assert processed[0].reminder_id == r1.reminder_id
    assert processed[0].status == ReminderStatus.COMPLETED
    assert processed[0].completed_at is not None
    assert len(delivered_msgs) == 1
    assert "Morning stretches" in delivered_msgs[0]

    # Re-running process_due_reminders at 10:10 is idempotent
    clock.advance(300.0)
    processed_idempotent = scheduler.process_due_reminders("eleanor")
    assert len(processed_idempotent) == 0

    # Advance to 14:01: r2 is due and processed
    clock.advance(13860.0)  # 14:01
    processed_r2 = scheduler.process_due_reminders("eleanor")
    assert len(processed_r2) == 1
    assert processed_r2[0].reminder_id == r2.reminder_id
    assert processed_r2[0].status == ReminderStatus.COMPLETED
    assert len(delivered_msgs) == 2


def test_reminder_scheduler_bridge_failure(temp_storage):
    clock = SimulatedClock(datetime(2026, 10, 21, 8, 0, 0, tzinfo=timezone.utc))

    class FailingBridge(ReminderDeliveryBridge):
        def deliver_reminder(self, reminder: Reminder) -> bool:
            raise ConnectionError("Speaker device offline")

    scheduler = ReminderScheduler(storage=temp_storage, clock=clock, delivery_bridge=FailingBridge())

    r = Reminder(
        person_id="eleanor",
        text="Eye drops",
        scheduled_time="08:15",
        created_at=clock.now(),
    )
    temp_storage.save_reminder(r)

    clock.advance(1000.0)  # past 08:15
    processed = scheduler.process_due_reminders("eleanor")
    assert len(processed) == 1
    assert processed[0].status == ReminderStatus.FAILED
    assert "Speaker device offline" in processed[0].error

    # Verify persisted in storage
    stored = temp_storage.get_reminders("eleanor", active_only=False)[0]
    assert stored.status == ReminderStatus.FAILED
    assert "Speaker device offline" in stored.error


def test_alexa_reminder_missing_components_documented():
    """Verify that CareLoop explicitly identifies the missing Alexa Echo components."""
    assert "api_endpoint" in ALEXA_REMINDER_DELIVERY_REQUIREMENTS
    assert "required_permission" in ALEXA_REMINDER_DELIVERY_REQUIREMENTS
    assert len(ALEXA_REMINDER_DELIVERY_REQUIREMENTS["missing_components"]) >= 3

    # Attempting to deliver via AlexaSkillRemindersBridge without token raises clear descriptive error
    bridge = AlexaSkillRemindersBridge(oauth_token=None)
    reminder = Reminder(
        person_id="eleanor",
        text="Blood pressure pill",
        scheduled_time="09:00",
    )
    with pytest.raises(RuntimeError) as exc_info:
        bridge.deliver_reminder(reminder)

    err = str(exc_info.value)
    assert "alexa::alerts:reminders:skill:readwrite" in err
    assert "Missing required Alexa Skill credentials" in err

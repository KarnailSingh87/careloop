"""
Unit tests for CareLoop storage layer (SQLiteStorage).
"""

from datetime import datetime, timezone
import os
import tempfile
import pytest

from careloop.models import Event, EventType, PersonProfile, EmergencyContact, Alert, AlertLevel, RoutineType
from careloop.server.models import Reminder, ReminderStatus
from careloop.storage.sqlite_store import SQLiteStorage


@pytest.fixture
def temp_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = SQLiteStorage(db_path=path)
    yield store
    store.close()
    if os.path.exists(path):
        os.remove(path)


def test_sqlite_save_and_get_events(temp_store):
    t1 = datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 20, 8, 30, 0, tzinfo=timezone.utc)

    e1 = Event(
        person_id="eleanor",
        event_type=EventType.PILL,
        timestamp=t1,
        metadata={"medication": "lisinopril"},
    )
    e2 = Event(
        person_id="eleanor",
        event_type=EventType.MEAL,
        timestamp=t2,
        metadata={"meal_type": "breakfast"},
    )
    temp_store.save_event(e1)
    temp_store.save_event(e2)

    # Latest first
    events = temp_store.get_events("eleanor", limit=10)
    assert len(events) == 2
    assert events[0].event_type == EventType.MEAL
    assert events[1].event_type == EventType.PILL

    # Filter by type
    pill_events = temp_store.get_events("eleanor", event_type="pill")
    assert len(pill_events) == 1
    assert pill_events[0].metadata["medication"] == "lisinopril"


def test_sqlite_reminders(temp_store):
    r1 = Reminder(
        person_id="eleanor",
        text="Drink water",
        scheduled_time="10:00",
        status=ReminderStatus.PENDING,
    )
    r2 = Reminder(
        person_id="eleanor",
        text="Lunch time",
        scheduled_time="12:30",
        status=ReminderStatus.COMPLETED,
    )
    temp_store.save_reminder(r1)
    temp_store.save_reminder(r2)

    active = temp_store.get_reminders("eleanor", active_only=True)
    assert len(active) == 1
    assert active[0].text == "Drink water"

    all_reminders = temp_store.get_reminders("eleanor", active_only=False)
    assert len(all_reminders) == 2


def test_sqlite_profile(temp_store):
    contact = EmergencyContact(
        name="Linda Davis",
        relationship="Daughter",
        phone="+1-555-019-2834",
    )
    profile = PersonProfile(
        person_id="eleanor",
        display_name="Eleanor Davis",
        timezone="America/New_York",
        emergency_contacts=[contact],
    )
    temp_store.save_profile(profile)

    fetched = temp_store.get_profile("eleanor")
    assert fetched is not None
    assert fetched.display_name == "Eleanor Davis"
    assert len(fetched.emergency_contacts) == 1
    assert fetched.emergency_contacts[0].phone == "+1-555-019-2834"

    # Non-existent person
    assert temp_store.get_profile("unknown") is None


def test_sqlite_alerts(temp_store):
    t = datetime(2026, 10, 20, 9, 30, 0, tzinfo=timezone.utc)
    alert = Alert(
        person_id="eleanor",
        level=AlertLevel.CRITICAL_ESCALATION,
        created_at=t,
        title="Missed morning medication",
        reasons=["Window closed at 09:15 UTC", "Voice checkin unanswered"],
        recommended_action="Call Linda Davis",
        routine_type=RoutineType.MORNING_MEDS,
        status="ACTIVE",
    )
    temp_store.save_alert(alert)

    alerts = temp_store.get_alerts("eleanor", active_only=True)
    assert len(alerts) == 1
    assert alerts[0].title == "Missed morning medication"
    assert len(alerts[0].reasons) == 2

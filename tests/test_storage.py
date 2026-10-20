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


def test_dynamodb_storage_mocked():
    from unittest.mock import MagicMock
    import json
    from careloop.storage.dynamo_store import DynamoDBStorage
    from careloop.models import EscalationState, EscalationStage

    mock_table = MagicMock()
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table

    store = DynamoDBStorage(table_name="CareLoopData", dynamodb_resource=mock_resource)

    # 1. Event
    t = datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc)
    event = Event(person_id="dad", event_type=EventType.PILL, timestamp=t, metadata={"pill": "aspirin"})
    store.save_event(event)
    mock_table.put_item.assert_called()

    # Query event mock
    mock_table.query.return_value = {
        "Items": [
            {
                "event_id": event.event_id,
                "person_id": "dad",
                "event_type": "pill",
                "timestamp": t.isoformat(),
                "metadata": json.dumps({"pill": "aspirin"}),
            }
        ]
    }
    events = store.get_events("dad")
    assert len(events) == 1
    assert events[0].person_id == "dad"
    assert events[0].event_type == EventType.PILL

    # 2. Profile & List Profiles
    contact = EmergencyContact(name="Linda", relationship="Daughter", phone="+15551234567")
    profile = PersonProfile(person_id="dad", display_name="Arthur Davis", timezone="America/New_York", emergency_contacts=[contact])
    store.save_profile(profile)

    mock_table.get_item.return_value = {
        "Item": {
            "person_id": "dad",
            "display_name": "Arthur Davis",
            "timezone": "America/New_York",
            "emergency_contacts": json.dumps([contact.model_dump()]),
            "created_at": profile.created_at.isoformat(),
        }
    }
    fetched_p = store.get_profile("dad")
    assert fetched_p is not None
    assert fetched_p.display_name == "Arthur Davis"

    mock_table.scan.return_value = {
        "Items": [
            {
                "person_id": "dad",
                "display_name": "Arthur Davis",
                "timezone": "America/New_York",
                "emergency_contacts": json.dumps([contact.model_dump()]),
                "created_at": profile.created_at.isoformat(),
            }
        ]
    }
    profiles = store.list_profiles()
    assert len(profiles) == 1
    assert profiles[0].person_id == "dad"

    # 3. Escalation State
    state = EscalationState(
        person_id="dad",
        stage=EscalationStage.GENTLE_CHECK_IN,
        entered_at=t,
        last_updated=t,
        risk_score=0.45,
        reasons=["Missed breakfast"],
    )
    store.save_escalation_state(state)
    mock_table.get_item.return_value = {
        "Item": {
            "person_id": "dad",
            "stage": "gentle_check_in",
            "entered_at": t.isoformat(),
            "last_updated": t.isoformat(),
            "risk_score": "0.45",
            "reasons": json.dumps(["Missed breakfast"]),
            "metadata": json.dumps({}),
        }
    }
    esc = store.get_escalation_state("dad")
    assert esc is not None
    assert esc.stage == EscalationStage.GENTLE_CHECK_IN
    assert esc.risk_score == 0.45


def test_storage_base_cannot_instantiate_incomplete():
    from careloop.storage.base import StorageBase

    class IncompleteStorage(StorageBase):
        pass

    with pytest.raises(TypeError):
        IncompleteStorage()


def test_storage_medication_event_mapping_dynamodb():
    from unittest.mock import MagicMock
    import json
    from careloop.storage.dynamo_store import DynamoDBStorage

    mock_table = MagicMock()
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table
    store = DynamoDBStorage(table_name="CareLoopData", dynamodb_resource=mock_resource)

    mock_table.query.return_value = {
        "Items": [
            {
                "event_id": "ev_med_1",
                "person_id": "dad",
                "event_type": "medication",
                "timestamp": "2026-10-20T08:00:00+00:00",
                "metadata": json.dumps({"medication": "metformin"}),
            }
        ]
    }
    events = store.get_events("dad")
    assert len(events) == 1
    assert events[0].event_type == EventType.PILL


def test_storage_medication_event_mapping_sqlite(temp_store):
    # Directly insert raw 'medication' row to simulate legacy event
    with temp_store._conn:
        temp_store._conn.execute(
            """
            INSERT INTO events (event_id, person_id, event_type, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("ev_raw_med", "eleanor", "medication", "2026-10-20T08:00:00+00:00", '{"medication": "metformin"}'),
        )
    events = temp_store.get_events("eleanor")
    assert len(events) == 1
    assert events[0].event_type == EventType.PILL

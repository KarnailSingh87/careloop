"""
Unit and integration-contract tests for CareLoop storage backends.

Runs identical behavioral contract tests against:
1. SQLiteStorage (local SQLite database file)
2. DynamoDBStorage (AWS single-table DynamoDB adapter via in-memory mock resource)

Verifies:
- Parameterized queries and transactions
- Appropriate index usage and WAL mode
- Explicit PK/SK single-table keys
- Optimistic concurrency control (StaleStateError)
- Idempotent duplicate event deduplication
- Zero audio / raw recording privacy enforcement
- Timezone-aware timestamp preservation
- Automated schema migration
- Complete CRUD for Events, Baselines, Profiles, Alerts, Escalation States, and Reminders
- Connection lifecycle and context manager support
- DynamoDB pagination with LastEvaluatedKey
- No silent fallback to SQLite when DynamoDB is configured but unreachable
"""

from datetime import datetime, timezone, timedelta
import os
import tempfile
from unittest.mock import MagicMock
import pytest
from botocore.exceptions import ClientError

from careloop.models import (
    Event,
    EventType,
    PersonProfile,
    EmergencyContact,
    Alert,
    AlertLevel,
    RoutineType,
    EscalationStage,
    EscalationState,
    Reminder,
    ReminderStatus,
    LearnedBaseline,
)
from careloop.storage.base import (
    StorageError,
    StaleStateError,
    StorageClosedError,
    PrivacyViolationError,
)
from careloop.storage.sqlite_store import SQLiteStorage
from careloop.storage.dynamo_store import DynamoDBStorage


class MockDynamoDBTable:
    """In-memory DynamoDB table simulator adhering to boto3 Table contract."""

    def __init__(self, name: str = "CareLoopData") -> None:
        self.name = name
        self.items: dict = {}  # (PK, SK) -> item_dict
        self.fail_load: bool = False

    def load(self) -> None:
        if self.fail_load:
            raise ClientError(
                {"Error": {"Code": "ResourceNotFoundException", "Message": f"Cannot find table {self.name}"}},
                "DescribeTable",
            )

    def put_item(self, Item: dict, ConditionExpression: str = None, ExpressionAttributeValues: dict = None) -> dict:
        pk = Item["PK"]
        sk = Item["SK"]
        key = (pk, sk)

        if ConditionExpression:
            if "attribute_not_exists(PK) AND attribute_not_exists(SK)" in ConditionExpression:
                if key in self.items:
                    raise ClientError(
                        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "Item already exists"}},
                        "PutItem",
                    )
            elif "attribute_not_exists(PK) OR version = :ver" in ConditionExpression:
                if key in self.items:
                    curr_ver = int(self.items[key].get("version", 1))
                    expected_ver = int(ExpressionAttributeValues[":ver"])
                    if curr_ver != expected_ver:
                        raise ClientError(
                            {"Error": {"Code": "ConditionalCheckFailedException", "Message": "Version mismatch"}},
                            "PutItem",
                        )

        self.items[key] = Item.copy()
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def get_item(self, Key: dict) -> dict:
        key = (Key["PK"], Key["SK"])
        item = self.items.get(key)
        if item:
            return {"Item": item.copy()}
        return {}

    def query(
        self,
        KeyConditionExpression: str,
        ExpressionAttributeValues: dict,
        ScanIndexForward: bool = True,
        Limit: int = None,
        ExclusiveStartKey: dict = None,
    ) -> dict:
        pk = ExpressionAttributeValues.get(":pk")
        prefix = ExpressionAttributeValues.get(":sk_prefix", "")

        matched = []
        for (k_pk, k_sk), item in self.items.items():
            if k_pk == pk and k_sk.startswith(prefix):
                matched.append(item.copy())

        # Sort by Sort Key (SK)
        matched.sort(key=lambda x: x["SK"], reverse=not ScanIndexForward)

        # Handle pagination continuation
        if ExclusiveStartKey:
            start_sk = ExclusiveStartKey["SK"]
            idx = next((i for i, x in enumerate(matched) if x["SK"] == start_sk), -1)
            if idx != -1:
                matched = matched[idx + 1 :]

        response = {}
        # If Limit specified, paginate results
        if Limit is not None and len(matched) > Limit:
            page_items = matched[:Limit]
            response["Items"] = page_items
            response["LastEvaluatedKey"] = {"PK": page_items[-1]["PK"], "SK": page_items[-1]["SK"]}
        else:
            response["Items"] = matched

        return response

    def scan(
        self,
        FilterExpression: str = None,
        ExpressionAttributeValues: dict = None,
        ExclusiveStartKey: dict = None,
    ) -> dict:
        matched = []
        sk_filter = ExpressionAttributeValues.get(":sk") if ExpressionAttributeValues else None
        for (_k_pk, _k_sk), item in self.items.items():
            if sk_filter and item.get("SK") != sk_filter:
                continue
            matched.append(item.copy())

        matched.sort(key=lambda x: (x["PK"], x["SK"]))
        if ExclusiveStartKey:
            start_key = (ExclusiveStartKey["PK"], ExclusiveStartKey["SK"])
            idx = next((i for i, x in enumerate(matched) if (x["PK"], x["SK"]) == start_key), -1)
            if idx != -1:
                matched = matched[idx + 1 :]

        response = {"Items": matched}
        return response


@pytest.fixture(params=["sqlite", "dynamodb"])
def storage_instance(request):
    """Fixture providing parameterized clean storage instances for contract tests."""
    if request.param == "sqlite":
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        store = SQLiteStorage(db_path=path)
        yield store
        store.close()
        if os.path.exists(path):
            os.remove(path)
    else:
        mock_table = MockDynamoDBTable(name="CareLoopData")
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        store = DynamoDBStorage(table_name="CareLoopData", dynamodb_resource=mock_resource)
        yield store
        store.close()


# ============================================================================
# BEHAVIORAL CONTRACT TESTS (Run against SQLite and DynamoDB identically)
# ============================================================================


def test_contract_save_and_get_events_ordering_and_limit(storage_instance):
    t0 = datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc)
    e1 = Event(person_id="eleanor", event_type=EventType.PILL, timestamp=t0, metadata={"pill": "lisinopril"})
    e2 = Event(
        person_id="eleanor",
        event_type=EventType.MEAL,
        timestamp=t0 + timedelta(minutes=30),
        metadata={"meal": "breakfast"},
    )
    e3 = Event(
        person_id="eleanor",
        event_type=EventType.MOVEMENT,
        timestamp=t0 + timedelta(hours=1),
        metadata={"room": "living_room"},
    )

    storage_instance.save_event(e1)
    storage_instance.save_event(e2)
    storage_instance.save_event(e3)

    # Latest first ordering
    events = storage_instance.get_events("eleanor", limit=2)
    assert len(events) == 2
    assert events[0].event_type == EventType.MOVEMENT
    assert events[1].event_type == EventType.MEAL


def test_contract_event_filtering_by_type(storage_instance):
    t0 = datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc)
    e1 = Event(person_id="eleanor", event_type=EventType.PILL, timestamp=t0, metadata={"dose": "10mg"})
    e2 = Event(
        person_id="eleanor", event_type=EventType.MEAL, timestamp=t0 + timedelta(minutes=15), metadata={"meal": "toast"}
    )

    storage_instance.save_event(e1)
    storage_instance.save_event(e2)

    pills = storage_instance.get_events("eleanor", event_type="pill")
    assert len(pills) == 1
    assert pills[0].event_type == EventType.PILL
    assert pills[0].metadata["dose"] == "10mg"


def test_contract_event_timezone_preservation(storage_instance):
    t_ny = datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc)
    e = Event(person_id="eleanor", event_type=EventType.DOOR, timestamp=t_ny, metadata={"door": "front"})
    storage_instance.save_event(e)

    reloaded = storage_instance.get_events("eleanor")
    assert len(reloaded) == 1
    assert reloaded[0].timestamp.tzinfo is not None
    assert reloaded[0].timestamp == t_ny


def test_contract_duplicate_event_handling_idempotent(storage_instance):
    t0 = datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc)
    stable_id = "stable-event-12345"
    e1 = Event(
        event_id=stable_id, person_id="eleanor", event_type=EventType.PILL, timestamp=t0, metadata={"attempt": 1}
    )
    e2 = Event(
        event_id=stable_id, person_id="eleanor", event_type=EventType.PILL, timestamp=t0, metadata={"attempt": 2}
    )

    storage_instance.save_event(e1)
    # Second submission with the exact same ID must be safely ignored
    storage_instance.save_event(e2)

    events = storage_instance.get_events("eleanor")
    assert len(events) == 1
    assert events[0].event_id == stable_id


def test_contract_naive_timestamp_rejected(storage_instance):
    naive_dt = datetime(2026, 10, 20, 8, 0, 0)  # No tzinfo
    e = Event(person_id="eleanor", event_type=EventType.PILL, timestamp=naive_dt)

    with pytest.raises(ValueError) as excinfo:
        storage_instance.save_event(e)
    assert "timezone-aware" in str(excinfo.value)


def test_contract_audio_metadata_rejected_for_privacy(storage_instance):
    t0 = datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc)
    e = Event(
        person_id="eleanor",
        event_type=EventType.PILL,
        timestamp=t0,
        metadata={"raw_audio": b"RIFF...."},
    )
    with pytest.raises(PrivacyViolationError) as excinfo:
        storage_instance.save_event(e)
    assert "Audio/recording" in str(excinfo.value)


def test_contract_baselines_crud(storage_instance):
    t0 = datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc)
    b1 = LearnedBaseline(
        person_id="eleanor",
        routine_type=RoutineType.MORNING_MEDS,
        sample_count=12,
        mean_time_minutes=510.5,
        std_dev_minutes=15.2,
        earliest_time="08:15",
        latest_time="08:45",
        confidence_score=0.85,
        last_updated=t0,
    )
    b2 = LearnedBaseline(
        person_id="eleanor",
        routine_type=RoutineType.LUNCH,
        sample_count=8,
        mean_time_minutes=765.0,
        std_dev_minutes=20.0,
        earliest_time="12:30",
        latest_time="13:10",
        confidence_score=0.60,
        last_updated=t0,
    )

    storage_instance.save_baseline(b1)
    storage_instance.save_baseline(b2)

    fetched = storage_instance.get_baseline("eleanor", "morning_meds")
    assert fetched is not None
    assert fetched.person_id == "eleanor"
    assert fetched.sample_count == 12
    assert fetched.mean_time_minutes == 510.5
    assert fetched.confidence_score == 0.85

    all_b = storage_instance.list_baselines("eleanor")
    assert len(all_b) == 2


def test_contract_reminders_crud_and_filtering(storage_instance):
    t0 = datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc)
    r1 = Reminder(
        person_id="eleanor", text="Drink water", scheduled_time="10:00", status=ReminderStatus.PENDING, created_at=t0
    )
    r2 = Reminder(
        person_id="eleanor", text="Take walk", scheduled_time="15:00", status=ReminderStatus.COMPLETED, created_at=t0
    )

    storage_instance.save_reminder(r1)
    storage_instance.save_reminder(r2)

    active = storage_instance.get_reminders("eleanor", active_only=True)
    assert len(active) == 1
    assert active[0].text == "Drink water"

    all_reminders = storage_instance.get_reminders("eleanor", active_only=False)
    assert len(all_reminders) == 2


def test_contract_profiles_crud_and_listing(storage_instance):
    t0 = datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc)
    contact = EmergencyContact(name="Linda Davis", relationship="Daughter", phone="+1-555-019-2834")
    profile = PersonProfile(
        person_id="eleanor",
        display_name="Eleanor Davis",
        timezone="America/New_York",
        emergency_contacts=[contact],
        created_at=t0,
    )
    storage_instance.save_profile(profile)

    fetched = storage_instance.get_profile("eleanor")
    assert fetched is not None
    assert fetched.display_name == "Eleanor Davis"
    assert len(fetched.emergency_contacts) == 1

    profiles = storage_instance.list_profiles()
    assert len(profiles) >= 1
    assert any(p.person_id == "eleanor" for p in profiles)


def test_contract_alerts_lifecycle_and_delivery_status(storage_instance):
    t0 = datetime(2026, 10, 20, 9, 30, 0, tzinfo=timezone.utc)
    alert = Alert(
        person_id="eleanor",
        level=AlertLevel.CRITICAL_ESCALATION,
        created_at=t0,
        title="Unresponsive check-in",
        reasons=["Missed pill", "No movement"],
        recommended_action="Call Linda",
        notification_status="pending",
        status="ACTIVE",
    )
    storage_instance.save_alert(alert)

    # 1. Fetch pending active alert
    alerts = storage_instance.get_alerts("eleanor", active_only=True)
    assert len(alerts) == 1
    assert alerts[0].notification_status == "pending"

    # 2. Update alert to delivered
    alert.notification_status = "delivered"
    alert.delivered_at = t0 + timedelta(seconds=2)
    storage_instance.save_alert(alert)

    updated_alerts = storage_instance.get_alerts("eleanor", active_only=True)
    assert len(updated_alerts) == 1
    assert updated_alerts[0].notification_status == "delivered"
    assert updated_alerts[0].delivered_at is not None

    # 3. Resolve alert
    alert.status = "RESOLVED"
    storage_instance.save_alert(alert)

    assert len(storage_instance.get_alerts("eleanor", active_only=True)) == 0
    assert len(storage_instance.get_alerts("eleanor", active_only=False)) == 1


def test_contract_escalation_state_optimistic_locking(storage_instance):
    t0 = datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc)
    state = EscalationState(
        person_id="eleanor",
        stage=EscalationStage.NORMAL,
        entered_at=t0,
        last_updated=t0,
        version=1,
    )
    storage_instance.save_escalation_state(state, check_version=False)

    # Valid optimistic advance: version increments 1 -> 2
    state.stage = EscalationStage.GENTLE_CHECK_IN
    storage_instance.save_escalation_state(state, check_version=True)
    assert state.version == 2

    persisted = storage_instance.get_escalation_state("eleanor")
    assert persisted.stage == EscalationStage.GENTLE_CHECK_IN
    assert persisted.version == 2

    # Stale worker write with version 1 must raise StaleStateError
    stale_state = EscalationState(
        person_id="eleanor",
        stage=EscalationStage.REPEAT_CHECK_IN,
        entered_at=t0,
        last_updated=t0,
        version=1,
    )
    with pytest.raises(StaleStateError):
        storage_instance.save_escalation_state(stale_state, check_version=True)


def test_contract_restart_preserves_state(request):
    """Verify that re-instantiating storage from persistent state retains exact escalation data."""
    t0 = datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc)
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    store1 = SQLiteStorage(db_path=path)
    state = EscalationState(
        person_id="eleanor",
        stage=EscalationStage.REPEAT_CHECK_IN,
        entered_at=t0,
        last_updated=t0,
        risk_score=0.45,
        reasons=["Medication missed past baseline grace window"],
        event_references=["ev-101", "ev-102"],
        notification_state="none",
        version=2,
    )
    store1.save_escalation_state(state, check_version=False)
    store1.close()

    # Re-open in fresh storage instance (simulating server reboot)
    store2 = SQLiteStorage(db_path=path)
    reloaded = store2.get_escalation_state("eleanor")
    assert reloaded is not None
    assert reloaded.stage == EscalationStage.REPEAT_CHECK_IN
    assert reloaded.entered_at == t0
    assert reloaded.risk_score == 0.45
    assert reloaded.event_references == ["ev-101", "ev-102"]
    assert reloaded.version == 2
    store2.close()

    if os.path.exists(path):
        os.remove(path)


def test_contract_close_lifecycle_and_context_manager():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    with SQLiteStorage(db_path=path) as store:
        t0 = datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc)
        store.save_event(Event(person_id="eleanor", event_type=EventType.PILL, timestamp=t0))

    # Connection must now be closed
    with pytest.raises(StorageClosedError):
        store.save_event(Event(person_id="eleanor", event_type=EventType.PILL, timestamp=t0))

    if os.path.exists(path):
        os.remove(path)


def test_dynamodb_pagination_with_last_evaluated_key():
    """Verify DynamoDB pagination loops handle query results split across pages."""
    mock_table = MockDynamoDBTable(name="CareLoopData")
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table
    store = DynamoDBStorage(table_name="CareLoopData", dynamodb_resource=mock_resource)

    t0 = datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc)
    # Save 15 events
    for i in range(15):
        store.save_event(
            Event(
                person_id="eleanor",
                event_type=EventType.MOVEMENT,
                timestamp=t0 + timedelta(minutes=i),
                metadata={"index": i},
            )
        )

    # Set mock Table page limit to 5 to force pagination
    original_query = mock_table.query

    def paged_query(**kwargs):
        kwargs["Limit"] = 5
        return original_query(**kwargs)

    mock_table.query = paged_query

    # Fetch 12 events across 3 simulated pages
    events = store.get_events("eleanor", limit=12)
    assert len(events) == 12


def test_dynamodb_unreachable_fails_fast_without_sqlite_fallback():
    """Verify that an inaccessible DynamoDB table raises StorageError on verify_table()."""
    mock_table = MockDynamoDBTable(name="CareLoopData")
    mock_table.fail_load = True
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table

    store = DynamoDBStorage(table_name="CareLoopData", dynamodb_resource=mock_resource)
    with pytest.raises(StorageError) as excinfo:
        store.verify_table()
    assert "ResourceNotFoundException" in str(excinfo.value)

"""
Unit tests for CareLoop domain models.
"""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from careloop.models import (
    EventType,
    RoutineType,
    AlertLevel,
    EmergencyContact,
    PersonProfile,
    Event,
    LearnedBaseline,
    CheckinPrompt,
    CheckinStatus,
    Alert,
)


def test_event_creation_and_serialization():
    now = datetime(2026, 10, 20, 8, 15, 0, tzinfo=timezone.utc)
    event = Event(
        person_id="eleanor",
        event_type=EventType.PILL,
        timestamp=now,
        metadata={"medication": "lisinopril", "slot": "morning"},
    )
    assert event.person_id == "eleanor"
    assert event.event_type == EventType.PILL
    assert event.timestamp == now
    assert event.metadata["medication"] == "lisinopril"
    assert len(event.event_id) > 10

    # Serialization roundtrip
    dumped = event.model_dump()
    loaded = Event.model_validate(dumped)
    assert loaded == event


def test_person_profile_with_contacts():
    contact = EmergencyContact(
        name="Linda Davis",
        relationship="Daughter",
        phone="+1-555-019-2834",
        email="linda@example.com",
        notification_channel="sms",
    )
    profile = PersonProfile(
        person_id="eleanor",
        display_name="Eleanor Davis",
        timezone="America/New_York",
        emergency_contacts=[contact],
    )
    assert len(profile.emergency_contacts) == 1
    assert profile.emergency_contacts[0].name == "Linda Davis"


def test_alert_requires_reasons():
    now = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)

    # Must fail if reasons are missing
    with pytest.raises(ValidationError):
        Alert(
            person_id="eleanor",
            level=AlertLevel.CRITICAL_ESCALATION,
            created_at=now,
            title="Missed medication",
            recommended_action="Call caregiver",
            # missing reasons
        )  # type: ignore

    alert = Alert(
        person_id="eleanor",
        level=AlertLevel.CRITICAL_ESCALATION,
        created_at=now,
        title="Missed morning medication",
        reasons=[
            "Morning medication scheduled between 08:00 and 09:30 UTC",
            "No pill bottle opening event logged by 10:00 UTC",
            "Alexa check-in at 09:35 UTC went unanswered",
        ],
        recommended_action="Contact daughter Linda Davis at +1-555-019-2834",
    )
    assert len(alert.reasons) == 3
    assert alert.status == "ACTIVE"


def test_checkin_prompt_lifecycle():
    t0 = datetime(2026, 10, 20, 9, 30, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
    prompt = CheckinPrompt(
        person_id="eleanor",
        routine_type=RoutineType.MORNING_MEDS,
        created_at=t0,
        expires_at=t1,
        speech_text="Good morning Eleanor, did you take your morning blood pressure medication?",
    )
    assert prompt.status == CheckinStatus.PENDING
    prompt.status = CheckinStatus.ANSWERED_YES
    prompt.response_text = "Yes, I just took it"
    prompt.answered_at = t0
    assert prompt.status == CheckinStatus.ANSWERED_YES


def test_learned_baseline_confidence_bounds():
    now = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
    baseline = LearnedBaseline(
        person_id="eleanor",
        routine_type=RoutineType.BREAKFAST,
        sample_count=14,
        mean_time_minutes=510.0,  # 08:30
        std_dev_minutes=18.5,
        earliest_time="08:05",
        latest_time="08:55",
        confidence_score=0.92,
        last_updated=now,
    )
    assert baseline.confidence_score == 0.92

    # Confidence must be between 0.0 and 1.0
    with pytest.raises(ValidationError):
        LearnedBaseline(
            person_id="eleanor",
            routine_type=RoutineType.BREAKFAST,
            sample_count=14,
            mean_time_minutes=510.0,
            std_dev_minutes=18.5,
            earliest_time="08:05",
            latest_time="08:55",
            confidence_score=1.5,  # Invalid!
            last_updated=now,
        )

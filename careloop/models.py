"""
Core domain models for CareLoop.

All models are strictly typed using Pydantic v2.
Only structured metadata is recorded—no raw audio or audio recordings are stored.
Every alert includes deterministic, human-readable explanations.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Supported routine event categories."""
    PILL = "pill"
    MEAL = "meal"
    MOVEMENT = "movement"
    DOOR = "door"
    CHECKIN_RESPONSE = "checkin_response"
    CUSTOM = "custom"


class RoutineType(str, Enum):
    """Standard elder daily routine types."""
    MORNING_MEDS = "morning_meds"
    EVENING_MEDS = "evening_meds"
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    MORNING_WAKEUP = "morning_wakeup"
    NIGHT_SLEEP = "night_sleep"
    GENERAL_ACTIVITY = "general_activity"


class AlertLevel(str, Enum):
    """Deterministic alert escalation levels."""
    INFO = "info"
    CHECKIN_REQUIRED = "checkin_required"
    MISSED_ROUTINE = "missed_routine"
    UNRESPONSIVE_CHECKIN = "unresponsive_checkin"
    ANOMALY_WARNING = "anomaly_warning"
    CRITICAL_ESCALATION = "critical_escalation"


class EscalationStage(str, Enum):
    """Persisted escalation state machine stages."""
    NORMAL = "normal"
    GENTLE_CHECK_IN = "gentle_check_in"
    REPEAT_CHECK_IN = "repeat_check_in"
    NOTIFY_FAMILY = "notify_family"


class EscalationState(BaseModel):
    """Persisted per-person escalation state."""
    person_id: str
    stage: EscalationStage = EscalationStage.NORMAL
    entered_at: datetime
    last_updated: datetime
    risk_score: float = 0.0
    reasons: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EmergencyContact(BaseModel):
    """Designated caregiver or family contact."""
    name: str
    relationship: str
    phone: str
    email: Optional[str] = None
    notification_channel: str = "sms"  # sms, sns, phone_call


class PersonProfile(BaseModel):
    """Elder parent profile configuration."""
    person_id: str
    display_name: str
    timezone: str = "UTC"
    emergency_contacts: List[EmergencyContact] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now())


class Event(BaseModel):
    """
    Routine event log entry.
    
    STRICT PRIVACY GUARANTEE:
    Only metadata (person, type, timestamp, optional tags) is captured.
    Raw audio or ambient sound is never recorded or stored.
    """
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    person_id: str
    event_type: EventType
    timestamp: datetime
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Non-audio metadata such as location, room, pill bottle id, or meal category."
    )


class RoutineRule(BaseModel):
    """
    Expected daily routine window configuration.
    
    Times are stored in HH:MM (24-hour UTC or local person-time).
    """
    routine_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    person_id: str
    routine_type: RoutineType
    event_type: EventType
    target_time: str = Field(description="Target time in HH:MM format (24-hour)")
    window_before_minutes: int = 45
    window_after_minutes: int = 60
    grace_period_minutes: int = 30
    requires_voice_checkin_first: bool = True
    is_critical: bool = True


class LearnedBaseline(BaseModel):
    """
    Dynamically learned schedule baseline from historical observations.
    Calculated purely via deterministic statistical methods (no LLM in the loop).
    """
    person_id: str
    routine_type: RoutineType
    sample_count: int
    mean_time_minutes: float = Field(description="Mean time in minutes from 00:00")
    std_dev_minutes: float = Field(description="Standard deviation in minutes")
    earliest_time: str = Field(description="HH:MM format")
    latest_time: str = Field(description="HH:MM format")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence based on sample size")
    last_updated: datetime


class CheckinStatus(str, Enum):
    PENDING = "pending"
    ANSWERED_YES = "answered_yes"
    ANSWERED_NO = "answered_no"
    EXPIRED_NO_RESPONSE = "expired_no_response"
    CANCELLED = "cancelled"


class CheckinPrompt(BaseModel):
    """Alexa voice check-in attempt record."""
    checkin_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    person_id: str
    routine_type: RoutineType
    created_at: datetime
    expires_at: datetime
    speech_text: str
    status: CheckinStatus = CheckinStatus.PENDING
    response_text: Optional[str] = None
    answered_at: Optional[datetime] = None


class Alert(BaseModel):
    """
    Deterministic alert dispatched to family or caregivers.
    
    RULE: Every alert MUST have explicit, human-readable reasons explaining
    the baseline, the observed data, and why an alert was triggered.
    """
    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    person_id: str
    level: AlertLevel
    created_at: datetime
    title: str
    reasons: List[str] = Field(
        ...,
        description="Human-readable deterministic reasons justifying this alert."
    )
    recommended_action: str
    routine_type: Optional[RoutineType] = None
    status: str = "ACTIVE"  # ACTIVE, ACKNOWLEDGED, RESOLVED
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReminderStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    DISMISSED = "dismissed"


class Reminder(BaseModel):
    """Voice reminder scheduled through Alexa+."""
    reminder_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    person_id: str
    text: str
    scheduled_time: str = Field(description="ISO 8601 string or HH:MM target time")
    status: ReminderStatus = ReminderStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now())

"""
Server data models and request schemas for CareLoop MCP server.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List
from pydantic import BaseModel, Field

# Re-export core models for server convenience
from careloop.models import Reminder, ReminderStatus  # noqa: F401


class RoutineEventType(str, Enum):
    """Specific routine event types accepted by Alexa+ MCP tools."""

    MEDICATION = "medication"
    MEAL = "meal"
    MOVEMENT = "movement"
    DOOR = "door"


class HealthStatus(BaseModel):
    """Routine health and anomaly assessment result."""

    person_id: str
    risk_level: str = "low"  # low, moderate, elevated, critical
    status: str = "nominal"
    message: str = "All monitored routines within nominal thresholds."
    last_evaluated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    active_alerts: List[str] = Field(default_factory=list)

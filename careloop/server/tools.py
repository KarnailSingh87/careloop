"""
Tool implementations for CareLoop MCP server.

Provides tools accessible to Alexa+:
- log_routine_event: Record routine events (medication, meal, movement, door)
- check_routine_health: Check routine health / risk assessment
- schedule_reminder: Schedule a voice reminder for the elder parent
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, Optional

from dateutil import parser as date_parser

try:
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:
    class ToolError(Exception):
        pass

from careloop.clock import Clock, SystemClock
from careloop.engine.baseline import BaselineEngine
from careloop.engine.risk import RiskEngine
from careloop.engine.escalation import EscalationEngine
from careloop.models import Event, EventType, EscalationStage
from careloop.server.models import Reminder, ReminderStatus, RoutineEventType
from careloop.storage.base import StorageBase

logger = logging.getLogger(__name__)

# Valid event types for log_routine_event
VALID_EVENT_TYPES = {
    "medication": EventType.PILL,
    "pill": EventType.PILL,
    "meal": EventType.MEAL,
    "movement": EventType.MOVEMENT,
    "door": EventType.DOOR,
}


def register_tools(
    server: Any,
    storage: StorageBase,
    clock: Clock,
    escalation_engine: Optional[EscalationEngine] = None,
    baseline_engine: Optional[BaselineEngine] = None,
) -> None:
    """Register all Alexa+ MCP tools onto the MCPServer instance."""
    if baseline_engine is None:
        baseline_engine = BaselineEngine()
    if escalation_engine is None:
        escalation_engine = EscalationEngine(
            storage=storage,
            baseline_engine=baseline_engine,
        )

    @server.tool()
    def log_routine_event(
        person: str,
        type: str,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Log an elderly parent routine event (medication, meal, movement, door).
        
        STRICT PRIVACY GUARANTEE:
        Only metadata (person, type, timestamp) is recorded.
        Raw audio or voice recordings are NEVER captured or stored.

        Parameters:
            person: Identifier of the person (e.g. "eleanor", "mom")
            type: Event category: 'medication', 'meal', 'movement', or 'door'
            timestamp: Optional ISO 8601 timestamp string (defaults to current clock time if None)
        """
        normalized_type = type.strip().lower()
        if normalized_type not in VALID_EVENT_TYPES:
            valid_options = ", ".join(sorted(VALID_EVENT_TYPES.keys()))
            raise ToolError(
                f"Invalid event type '{type}'. Allowed types are: {valid_options}"
            )

        event_type = VALID_EVENT_TYPES[normalized_type]

        if timestamp:
            try:
                parsed_time = date_parser.parse(timestamp)
                if parsed_time.tzinfo is None:
                    parsed_time = parsed_time.replace(tzinfo=timezone.utc)
                event_time = parsed_time.astimezone(timezone.utc)
            except Exception as e:
                raise ToolError(f"Could not parse timestamp '{timestamp}': {e}")
        else:
            event_time = clock.now()

        event = Event(
            person_id=person.strip().lower(),
            event_type=event_type,
            timestamp=event_time,
            metadata={"source": "alexa_plus", "raw_type": type},
        )

        storage.save_event(event)

        # Update baseline statistics
        baseline_engine.record_event(event.person_id, event.event_type.value, event.timestamp)

        # Any new event resets escalation back to normal
        escalation_engine.reset_to_normal(
            event.person_id,
            now=event_time,
            reason=f"Observed new routine event: {event.event_type.value}",
        )

        logger.info(
            f"Logged event {event.event_id}: person={event.person_id}, "
            f"type={event.event_type.value}, time={event.timestamp.isoformat()}"
        )

        return {
            "status": "logged",
            "event_id": event.event_id,
            "person": event.person_id,
            "type": event.event_type.value,
            "timestamp": event.timestamp.isoformat(),
        }

    @server.tool()
    def check_routine_health(person: str) -> Dict[str, Any]:
        """
        Evaluate routine health, risk score, plain-English reasons, and escalation stage.
        """
        person_id = person.strip().lower()
        now = clock.now()

        # Advance state machine via tick
        state = escalation_engine.tick(person_id, now)

        risk_level = "low"
        if state.risk_score >= 0.6:
            risk_level = "high"
        elif state.risk_score >= 0.3:
            risk_level = "medium"

        logger.info(
            f"Routine health check for {person_id}: risk_level={risk_level}, "
            f"score={state.risk_score}, stage={state.stage.value}"
        )

        return {
            "person": person_id,
            "risk_level": risk_level,
            "risk_score": state.risk_score,
            "reasons": state.reasons,
            "escalation_stage": state.stage.value,
            "last_evaluated": now.isoformat(),
        }

    @server.tool()
    def respond_to_checkin(person: str, response_text: str) -> Dict[str, Any]:
        """
        Record the elder parent's response to an Alexa check-in prompt.
        If the elder replies 'I'm fine' or confirms they are okay, resets escalation to normal.
        """
        person_id = person.strip().lower()
        now = clock.now()
        state = escalation_engine.handle_voice_response(person_id, response_text, now)
        return {
            "person": person_id,
            "response_recorded": response_text,
            "escalation_stage": state.stage.value,
            "message": f"Escalation stage is now {state.stage.value}.",
        }

    @server.tool()
    def schedule_reminder(person: str, text: str, time: str) -> Dict[str, Any]:
        """
        Schedule a voice reminder through Alexa+ for an elderly parent.

        Parameters:
            person: Identifier of the person (e.g. "eleanor", "mom")
            text: Reminder content to be announced (e.g. "Drink water and take blood pressure pill")
            time: Target scheduled time (ISO 8601 string or HH:MM time)
        """
        reminder = Reminder(
            person_id=person.strip().lower(),
            text=text.strip(),
            scheduled_time=time.strip(),
            status=ReminderStatus.PENDING,
            created_at=clock.now(),
        )

        storage.save_reminder(reminder)

        logger.info(
            f"Scheduled reminder {reminder.reminder_id}: person={reminder.person_id}, "
            f"time={reminder.scheduled_time}, text='{reminder.text}'"
        )

        return {
            "status": "scheduled",
            "reminder_id": reminder.reminder_id,
            "person": reminder.person_id,
            "text": reminder.text,
            "time": reminder.scheduled_time,
        }

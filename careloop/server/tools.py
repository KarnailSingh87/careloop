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
from careloop.llm.bedrock import BedrockAssistant
from careloop.models import Event, EventType, EscalationStage, Alert, AlertLevel
from careloop.notifier import NotifierBase, get_default_notifier
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
    notifier: Optional[NotifierBase] = None,
    llm_assistant: Optional[BedrockAssistant] = None,
) -> None:
    """Register all Alexa+ MCP tools onto the MCPServer instance."""
    if baseline_engine is None:
        baseline_engine = BaselineEngine()
    if notifier is None:
        notifier = get_default_notifier()
    if escalation_engine is None:
        escalation_engine = EscalationEngine(
            storage=storage,
            baseline_engine=baseline_engine,
            notifier=notifier,
        )
    if llm_assistant is None:
        llm_assistant = BedrockAssistant()

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

    @server.tool()
    def notify_family(person: str, severity: str, message: str) -> Dict[str, Any]:
        """
        Dispatches an urgent or warning alert notification to the elder parent's designated family caregivers via Amazon SNS (or console).
        Always logs the alert with supporting deterministic reasons to the audit history.

        Parameters:
            person: Identifier of the elder parent (e.g. 'eleanor', 'mom')
            severity: Alert severity level: 'low', 'medium', 'high', or 'critical'
            message: Plain-English explanation of why family is being alerted
        """
        person_id = person.strip().lower()
        now = clock.now()

        profile = storage.get_profile(person_id)
        contacts = profile.emergency_contacts if profile else []

        esc_state = escalation_engine.get_or_create_state(person_id, now)
        reasons = esc_state.reasons.copy() if esc_state.reasons else [f"Alert dispatched: {message}"]

        level_map = {
            "low": AlertLevel.INFO,
            "medium": AlertLevel.ANOMALY_WARNING,
            "high": AlertLevel.CRITICAL_ESCALATION,
            "critical": AlertLevel.CRITICAL_ESCALATION,
        }
        alert_level = level_map.get(severity.lower(), AlertLevel.ANOMALY_WARNING)

        alert = Alert(
            person_id=person_id,
            level=alert_level,
            created_at=now,
            title=f"CareLoop Family Alert: {message}",
            reasons=reasons,
            recommended_action="Contact elder parent directly or check the home monitoring dashboard.",
            status="ACTIVE",
            metadata={"severity": severity, "source": "notify_family_tool"},
        )
        storage.save_alert(alert)

        delivery_success = notifier.send_notification(
            person_id=person_id,
            severity=severity,
            message=message,
            reasons=reasons,
            contacts=contacts,
        )

        return {
            "status": "notified" if delivery_success else "dispatch_failed",
            "alert_id": alert.alert_id,
            "person": person_id,
            "severity": severity,
            "message": message,
            "notifier": notifier.__class__.__name__,
            "reasons": reasons,
            "delivered_to": [c.name for c in contacts] if contacts else ["Default Caregiver"],
        }

    @server.tool()
    def confirm_ok(person: str) -> Dict[str, Any]:
        """
        Called when an elderly parent responds to a voice check-in confirming they are fine, healthy, or okay.
        Resets any active routine check-in escalation state machine back to normal.

        Parameters:
            person: Identifier of the elder parent (e.g. 'eleanor', 'mom')
        """
        person_id = person.strip().lower()
        now = clock.now()
        state = escalation_engine.reset_to_normal(
            person_id=person_id,
            now=now,
            reason="Elder confirmed they are fine",
        )
        return {
            "status": "confirmed_ok",
            "person": person_id,
            "escalation_stage": state.stage.value,
            "message": f"Confirmed that {person_id} is okay. Escalation state is now normal.",
        }

    @server.tool()
    def daily_summary(person: str, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Generates a warm, empathetic daily routine summary for family caregivers using Amazon Bedrock.
        Summarizes medication checks, meals, and general movement patterns for a specific date.

        Parameters:
            person: Identifier of the elder parent (e.g. 'eleanor', 'mom')
            date: Optional target date string (YYYY-MM-DD or 'today'). Defaults to today.
        """
        person_id = person.strip().lower()
        now = clock.now()

        if not date or date.strip().lower() == "today":
            target_date = now.date()
            date_str = target_date.isoformat()
        else:
            try:
                target_date = date_parser.parse(date).date()
                date_str = target_date.isoformat()
            except Exception:
                target_date = now.date()
                date_str = target_date.isoformat()

        all_events = storage.get_events(person_id, limit=200)
        events_on_date = [e for e in all_events if e.timestamp.date() == target_date]

        profile = storage.get_profile(person_id)
        display_name = profile.display_name if profile else person_id.capitalize()

        summary_text = llm_assistant.daily_summary(
            person=person_id,
            target_date=target_date,
            storage=storage,
            display_name=display_name,
        )

        return {
            "person": person_id,
            "date": date_str,
            "event_count": len(events_on_date),
            "summary": summary_text,
        }

    @server.tool()
    def ask_memory(person: str, question: str) -> Dict[str, Any]:
        """
        Answers caregiver questions about the elder parent's daily routine history, habits, and recorded events.
        Uses Amazon Bedrock memory Q&A sandboxed strictly to factual event logs.

        Parameters:
            person: Identifier of the elder parent (e.g. 'eleanor', 'mom')
            question: Specific query about the parent's routine (e.g. 'Did Mom take her pills today?')
        """
        person_id = person.strip().lower()
        now = clock.now()
        profile = storage.get_profile(person_id)
        display_name = profile.display_name if profile else person_id.capitalize()

        answer = llm_assistant.ask_memory(
            person=person_id,
            question=question.strip(),
            storage=storage,
            now=now,
            display_name=display_name,
        )

        return {
            "person": person_id,
            "question": question,
            "answer": answer,
        }

    @server.tool()
    def tick_escalation(person: Optional[str] = None) -> Dict[str, Any]:
        """
        Runs a scheduled routine check and advances the escalation state machine without waiting for user requests.

        Parameters:
            person: Optional identifier of the elder parent. If omitted, ticks all known persons.
        """
        now = clock.now()
        if person:
            p_id = person.strip().lower()
            state = escalation_engine.tick(p_id, now)
            return {
                "status": "ticked",
                "timestamp": now.isoformat(),
                "person": p_id,
                "stage": state.stage.value,
                "risk_score": state.risk_score,
                "reasons": state.reasons,
            }
        else:
            results: Dict[str, Any] = {}
            known_persons = ["eleanor"]
            for p_id in known_persons:
                st = escalation_engine.tick(p_id, now)
                results[p_id] = {
                    "stage": st.stage.value,
                    "risk_score": st.risk_score,
                    "reasons": st.reasons,
                }
            return {
                "status": "ticked",
                "timestamp": now.isoformat(),
                "persons": results,
            }

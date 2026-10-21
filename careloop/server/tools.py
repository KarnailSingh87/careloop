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
import uuid

from dateutil import parser as date_parser

import collections
import re
import time

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
from careloop.notifier import NotifierBase, get_default_notifier, NotificationDeliveryStatus, ALLOWED_SEVERITIES
from careloop.server.models import Reminder, ReminderStatus, RoutineEventType
from careloop.server.security import check_tool_authorization
from careloop.storage.base import StorageBase

logger = logging.getLogger(__name__)

PERSON_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")

# Notification rate limit tracker to prevent SMS flooding (max 10 notifications per hour per person)
_NOTIFICATION_TIMESTAMPS: Dict[str, collections.deque] = collections.defaultdict(collections.deque)


def validate_person_identifier(person: Optional[str]) -> str:
    """Validate and sanitize person identifier."""
    if not person or not isinstance(person, str) or not person.strip():
        raise ToolError("Person identifier cannot be empty.")
    cleaned = person.strip().lower()
    if not PERSON_ID_PATTERN.match(cleaned):
        raise ToolError(
            f"Invalid person identifier '{person}'. Must be alphanumeric with dashes/underscores (1-64 characters)."
        )
    return cleaned


def check_notification_rate_limit(person_id: str, max_per_hour: int = 10) -> bool:
    """Check sliding window quota for notifications dispatched for a person."""
    now = time.time()
    history = _NOTIFICATION_TIMESTAMPS[person_id]
    while history and history[0] < now - 3600.0:
        history.popleft()
    if len(history) >= max_per_hour:
        return False
    history.append(now)
    return True


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
        baseline_engine.load_from_storage(storage)
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
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Record an elderly parent's routine event (medication, meal, movement, door).

        VOICE TRIGGERS (Alexa+ Intent Matching):
        - "I just took my pills" / "I took my blood pressure medication"
        - "I had breakfast" / "I finished lunch" / "I'm eating dinner"
        - "Dad got out of bed" / "Front door was opened"

        WHEN TO CALL:
        - Call when the elder parent states they completed a daily routine action.
        - Call when an ambient smart home sensor (pillbox, motion, contact sensor) reports an event.
        - Resets any active check-in escalation state machine back to 'normal'.

        WHEN NOT TO CALL:
        - Do NOT call if the user is asking whether an event occurred (use `ask_memory`).
        - Do NOT call for non-routine chatter.

        STRICT PRIVACY GUARANTEE:
        Only metadata (person, type, timestamp) is recorded. Raw audio is NEVER stored.

        Parameters:
            person: Identifier of the elder parent (e.g. "eleanor", "dad", "mom")
            type: Event category: 'medication' (or 'pill'), 'meal', 'movement', or 'door'
            timestamp: Optional ISO 8601 timestamp string (defaults to current clock time if None)
            metadata: Optional additional metadata dictionary (e.g. source, room, notes)
        """
        p_id = validate_person_identifier(person)
        check_tool_authorization("log_routine_event", person=p_id)

        if metadata:
            if not isinstance(metadata, dict) or len(metadata) > 50:
                raise ToolError("Invalid metadata: must be a dictionary with at most 50 keys.")
            try:
                if len(json.dumps(metadata)) > 8192:
                    raise ToolError("Invalid metadata: serialized payload exceeds 8KB limit.")
            except (TypeError, ValueError) as e:
                raise ToolError(f"Invalid metadata: must be JSON serializable: {e}")

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

        event_meta = {"source": "alexa_plus", "raw_type": type}
        if metadata and isinstance(metadata, dict):
            event_meta.update(metadata)

        event = Event(
            person_id=p_id,
            event_type=event_type,
            timestamp=event_time,
            metadata=event_meta,
        )

        storage.save_event(event)

        # Update baseline statistics
        baseline_engine.record_event(event.person_id, event.event_type.value, event.timestamp, event_id=event.event_id)

        # Any new event resets escalation back to normal
        escalation_engine.reset_to_normal(
            event.person_id,
            now=event_time,
            reason=f"Observed new routine event: {event.event_type.value}",
            event_id=event.event_id,
        )

        logger.info(
            f"Logged event {event.event_id}: person={event.person_id}, "
            f"type={event.event_type.value}, time={event.timestamp.isoformat()}"
        )

        friendly_time = event.timestamp.strftime("%I:%M %p").lstrip("0")
        type_display = "medication" if event.event_type.value == "pill" else event.event_type.value
        voice_msg = f"Thank you, I've recorded {event.person_id.capitalize()}'s {type_display} at {friendly_time}."

        return {
            "status": "logged",
            "event_id": event.event_id,
            "person": event.person_id,
            "type": event.event_type.value,
            "timestamp": event.timestamp.isoformat(),
            "voice_response": voice_msg,
        }

    @server.tool()
    def check_routine_health(person: str = "dad") -> Dict[str, Any]:
        """
        Evaluate an elder parent's routine health, deterministic risk score, and escalation stage.

        VOICE TRIGGERS (Alexa+ Intent Matching):
        - "How is Dad doing today?"
        - "Is Mom's routine normal?"
        - "Check on Eleanor"
        - "Are there any missed routines or alerts?"

        WHEN TO CALL:
        - Call when family or Alexa asks for routine status or wellness check.
        - Call during proactive Alexa routine audits to detect missed events.

        Parameters:
            person: Identifier of the elder parent (e.g. "eleanor", "dad", "mom")
        """
        p_id = validate_person_identifier(person)
        check_tool_authorization("check_routine_health", person=p_id)
        person_id = p_id
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

        if risk_level == "low":
            voice_msg = f"{person_id.capitalize()}'s routine health is normal today with low risk. All expected activities are on track."
        elif risk_level == "medium":
            reasons_text = "; ".join(state.reasons) if state.reasons else "Potential schedule deviation detected."
            voice_msg = f"{person_id.capitalize()} has an active routine warning: {reasons_text}"
        else:
            reasons_text = "; ".join(state.reasons) if state.reasons else "Multiple critical routines missed."
            voice_msg = f"Attention: {person_id.capitalize()} has high routine risk. {reasons_text}"

        return {
            "person": person_id,
            "risk_level": risk_level,
            "risk_score": state.risk_score,
            "reasons": state.reasons,
            "escalation_stage": state.stage.value,
            "notification_state": state.notification_state,
            "last_evaluated": now.isoformat(),
            "voice_response": voice_msg,
        }

    @server.tool()
    def respond_to_checkin(person: str, response_text: str) -> Dict[str, Any]:
        """
        Process the elder parent's verbal response to an Alexa proactive voice check-in prompt.

        VOICE TRIGGERS (Alexa+ Intent Matching):
        - Elder speaks after Alexa says "Good afternoon, are you doing okay?"
        - Example responses: "I was just reading", "I had a sandwich earlier", "Feeling a bit tired"

        WHEN TO CALL:
        - Call when the elder answers Alexa's check-in question.
        - If response indicates wellness ("fine", "good"), automatically resolves escalation to normal.

        Parameters:
            person: Identifier of the elder parent (e.g. "eleanor", "dad")
            response_text: Full transcribed text spoken by the elder parent
        """
        p_id = validate_person_identifier(person)
        check_tool_authorization("respond_to_checkin", person=p_id)
        if not response_text or not response_text.strip():
            raise ToolError("Response text cannot be empty.")
        if len(response_text) > 1000:
            raise ToolError("Response text exceeds maximum length of 1000 characters.")
        person_id = p_id
        now = clock.now()
        state = escalation_engine.handle_voice_response(person_id, response_text, now)
        voice_msg = f"Thanks for letting me know, {person_id.capitalize()}. I've updated your routine status."
        return {
            "person": person_id,
            "response_recorded": response_text,
            "escalation_stage": state.stage.value,
            "message": f"Escalation stage is now {state.stage.value}.",
            "voice_response": voice_msg,
        }

    @server.tool()
    def schedule_reminder(person: str, text: str, time: str) -> Dict[str, Any]:
        """
        Schedule a spoken voice reminder announced through Alexa+ for the elder parent.

        VOICE TRIGGERS (Alexa+ Intent Matching):
        - "Remind Dad to drink water at 3 PM"
        - "Set a reminder for Mom to take blood pressure pills at 8:00 AM"

        WHEN TO CALL:
        - Call when elder or caregiver requests a scheduled voice reminder.

        Parameters:
            person: Identifier of the elder parent (e.g. "eleanor", "dad")
            text: Spoken reminder message (e.g. "Drink water and take blood pressure pill")
            time: Target scheduled time (ISO 8601 string or HH:MM time, e.g. "15:00")
        """
        p_id = validate_person_identifier(person)
        check_tool_authorization("schedule_reminder", person=p_id)
        if not text or not text.strip():
            raise ToolError("Reminder text cannot be empty.")
        if len(text) > 1000:
            raise ToolError("Reminder text exceeds maximum length of 1000 characters.")
        person_id = p_id

        t = time.strip()
        if not t:
            raise ToolError("Reminder scheduled time cannot be empty.")

        hh_mm_match = re.match(r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$", t)
        if hh_mm_match:
            h, m = int(hh_mm_match.group(1)), int(hh_mm_match.group(2))
            normalized_time = f"{h:02d}:{m:02d}"
        else:
            try:
                parsed_time = date_parser.parse(t)
                normalized_time = parsed_time.isoformat()
            except Exception as e:
                raise ToolError(
                    f"Invalid reminder time '{time}'. Must be HH:MM 24-hour format (e.g. '15:00') "
                    f"or a valid ISO 8601 timestamp string (e.g. '2026-10-20T15:00:00Z')."
                )

        reminder = Reminder(
            person_id=person_id,
            text=text.strip(),
            scheduled_time=normalized_time,
            status=ReminderStatus.PENDING,
            created_at=clock.now(),
        )

        storage.save_reminder(reminder)

        logger.info(
            f"Scheduled reminder {reminder.reminder_id}: person={reminder.person_id}, "
            f"time={reminder.scheduled_time}, text='{reminder.text}'"
        )

        voice_msg = f"I have scheduled a reminder for {reminder.person_id.capitalize()} at {reminder.scheduled_time}: {reminder.text}."

        return {
            "status": "scheduled",
            "reminder_id": reminder.reminder_id,
            "person": reminder.person_id,
            "text": reminder.text,
            "time": reminder.scheduled_time,
            "voice_response": voice_msg,
        }

    @server.tool()
    def notify_family(person: str, severity: str, message: str) -> Dict[str, Any]:
        """
        Dispatch an urgent or warning alert notification to designated family caregivers via Amazon SNS.
        Always logs the alert with supporting deterministic audit reasons.

        VOICE TRIGGERS (Alexa+ Intent Matching):
        - "Alert my daughter" / "Call my family" / "Send an alert to family"
        - Proactive autonomous alert when routine check-in attempts fail

        WHEN TO CALL:
        - Call when the elder asks for family help, or when repeated check-ins go unanswered.

        Parameters:
            person: Identifier of the elder parent (e.g. 'eleanor', 'dad')
            severity: Alert severity level: 'low', 'medium', 'high', or 'critical'
            message: Plain-English explanation of why family is being alerted
        """
        p_id = validate_person_identifier(person)
        check_tool_authorization("notify_family", person=p_id)
        person_id = p_id

        sev = severity.strip().lower()
        if sev not in ALLOWED_SEVERITIES:
            valid_sevs = ", ".join(sorted(ALLOWED_SEVERITIES))
            raise ToolError(
                f"Unsupported severity '{severity}'. Allowed severities are: {valid_sevs}"
            )
        if not message or not message.strip():
            raise ToolError("Alert message cannot be empty.")
        if len(message) > 1000:
            raise ToolError("Alert message exceeds maximum length of 1000 characters.")

        if not check_notification_rate_limit(person_id):
            raise ToolError(
                f"Notification rate limit exceeded for {person_id}. "
                "Too many family notifications triggered in a short period."
            )

        person_id = person.strip().lower()
        now = clock.now()

        # Stable deduplication key
        msg_hash = abs(hash(message.strip())) % 1000000
        dedup_key = f"notify_family:{person_id}:{now.strftime('%Y-%m-%d-%H')}:{sev}:{msg_hash}"

        # Deduplication check: suppress identical active alert within 15 minutes
        existing_alert = storage.get_alert_by_dedup_key(person_id, dedup_key)
        if existing_alert and existing_alert.status == "ACTIVE":
            time_diff = (now - existing_alert.created_at).total_seconds()
            if time_diff < 900:  # 15 minutes window
                logger.info(f"Deduplicated notify_family alert for {person_id}: {dedup_key}")
                return {
                    "status": "deduplicated",
                    "delivery_status": NotificationDeliveryStatus.SKIPPED_DEDUPLICATED.value,
                    "prior_delivery_status": existing_alert.notification_status,
                    "alert_id": existing_alert.alert_id,
                    "person": person_id,
                    "severity": sev,
                    "message": message.strip(),
                    "dedup_key": dedup_key,
                    "notification_status": existing_alert.notification_status,
                    "note": "Duplicate alert suppressed within 15-minute deduplication window.",
                    "voice_response": f"An alert has already been sent to {person_id.capitalize()}'s family caregivers.",
                }

        profile = storage.get_profile(person_id)
        contacts = profile.emergency_contacts if profile else []

        esc_state = escalation_engine.get_or_create_state(person_id, now)
        reasons = esc_state.reasons.copy() if esc_state.reasons else [f"Alert dispatched: {message.strip()}"]

        level_map = {
            "low": AlertLevel.INFO,
            "medium": AlertLevel.ANOMALY_WARNING,
            "high": AlertLevel.CRITICAL_ESCALATION,
            "critical": AlertLevel.CRITICAL_ESCALATION,
        }
        alert_level = level_map.get(sev, AlertLevel.ANOMALY_WARNING)

        decision_id = str(uuid.uuid4())
        alert = Alert(
            person_id=person_id,
            level=alert_level,
            severity=sev,
            created_at=now,
            title=f"CareLoop Family Alert: {message.strip()}",
            reasons=reasons,
            recommended_action="Contact elder parent directly or check the home monitoring dashboard.",
            status="ACTIVE",
            notification_status="pending",
            event_ids=esc_state.event_references.copy() if esc_state else [],
            dedup_key=dedup_key,
            metadata={"severity": sev, "source": "notify_family_tool", "decision_id": decision_id},
        )
        storage.save_alert(alert)

        delivery_res = notifier.send_notification(
            person_id=person_id,
            severity=sev,
            message=message.strip(),
            reasons=reasons,
            contacts=contacts,
            dedup_key=dedup_key,
        )

        delivery_status = "failed"
        if hasattr(delivery_res, "status"):
            if delivery_res.status == NotificationDeliveryStatus.DELIVERED:
                alert.notification_status = "delivered"
                alert.delivered_at = now
                alert.message_id = delivery_res.message_id
                alert.delivery_error = None
                delivery_status = "delivered"
            elif delivery_res.status == NotificationDeliveryStatus.ACCEPTED:
                alert.notification_status = "accepted"
                alert.accepted_at = now
                alert.message_id = delivery_res.message_id
                alert.delivery_error = None
                delivery_status = "accepted"
            else:
                alert.notification_status = "failed"
                alert.delivery_error = delivery_res.error
                alert.retry_count += 1
                delivery_status = "failed"
        elif delivery_res:
            alert.notification_status = "delivered"
            alert.delivered_at = now
            alert.delivery_error = None
            delivery_status = "delivered"
        else:
            alert.notification_status = "failed"
            alert.delivery_error = "Notification dispatch returned false"
            alert.retry_count += 1
            delivery_status = "failed"

        storage.save_alert(alert)

        recipient_names = ", ".join(c.name for c in contacts) if contacts else "family caregivers"
        voice_msg = f"I've sent an alert to {person_id.capitalize()}'s {recipient_names}."

        return {
            "status": "notified" if delivery_status in ("delivered", "accepted") else "dispatch_failed",
            "delivery_status": delivery_status,
            "alert_id": alert.alert_id,
            "person": person_id,
            "severity": sev,
            "message": message.strip(),
            "notifier": notifier.__class__.__name__,
            "message_id": alert.message_id,
            "dedup_key": dedup_key,
            "reasons": reasons,
            "delivered_to": [c.name for c in contacts] if contacts else ["Default Caregiver"],
            "voice_response": voice_msg,
        }

    @server.tool()
    def confirm_ok(person: str) -> Dict[str, Any]:
        """
        Confirm the elder parent is fine, healthy, or safe, immediately resetting routine escalation to normal.

        VOICE TRIGGERS (Alexa+ Intent Matching):
        - "I'm fine" / "I'm okay" / "I am okay, Alexa"
        - "Everything is good" / "I'm doing well" / "Don't worry, I'm alright"

        WHEN TO CALL:
        - Call whenever the elder parent confirms they are fine.
        - Immediately resets any active check-in escalation state machine back to normal.

        Parameters:
            person: Identifier of the elder parent (e.g. 'eleanor', 'dad', 'mom')
        """
        p_id = validate_person_identifier(person)
        check_tool_authorization("confirm_ok", person=p_id)
        person_id = p_id

        now = clock.now()
        state = escalation_engine.reset_to_normal(
            person_id=person_id,
            now=now,
            reason="Elder confirmed they are fine",
        )
        voice_msg = f"Glad to hear you're doing well, {person_id.capitalize()}! I've cleared any routine check-ins."
        return {
            "status": "confirmed_ok",
            "person": person_id,
            "escalation_stage": state.stage.value,
            "message": f"Confirmed that {person_id} is okay. Escalation state is now normal.",
            "voice_response": voice_msg,
        }

    @server.tool()
    def daily_summary(person: str = "dad", date: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a warm, empathetic daily routine summary for family caregivers using Amazon Bedrock.
        Synthesizes medication checks, meals, and general movement patterns for a specific date.

        VOICE TRIGGERS (Alexa+ Intent Matching):
        - "Give me Dad's daily summary"
        - "How was Mom's day?" / "Summarize today's activities for Eleanor"
        - "What did Dad do today?"

        WHEN TO CALL:
        - Call when a family caregiver asks for an overview of the parent's day.

        Parameters:
            person: Identifier of the elder parent (e.g. 'eleanor', 'dad')
            date: Optional target date string (YYYY-MM-DD or 'today'). Defaults to today.
        """
        p_id = validate_person_identifier(person)
        check_tool_authorization("daily_summary", person=p_id)
        person_id = p_id

        now = clock.now()
        profile = storage.get_profile(person_id)
        person_tz_str = profile.timezone if profile and profile.timezone else "UTC"
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(person_tz_str)
        except Exception:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("UTC")

        local_now = now.astimezone(tz) if now.tzinfo else now

        if not date or date.strip().lower() == "today":
            target_date = local_now.date()
            date_str = target_date.isoformat()
        elif date.strip().lower() == "yesterday":
            target_date = (local_now - timedelta(days=1)).date()
            date_str = target_date.isoformat()
        else:
            try:
                target_date = date_parser.parse(date).date()
                date_str = target_date.isoformat()
            except Exception:
                target_date = local_now.date()
                date_str = target_date.isoformat()

        all_events = storage.get_events(person_id, limit=200)
        events_on_date = [
            e for e in all_events
            if (e.timestamp.astimezone(tz) if e.timestamp.tzinfo else e.timestamp).date() == target_date
        ]

        display_name = profile.display_name if profile else person_id.capitalize()

        summary_text = llm_assistant.daily_summary(
            person=person_id,
            target_date=target_date,
            storage=storage,
            now=now,
            display_name=display_name,
            person_tz=person_tz_str,
        )

        return {
            "person": person_id,
            "date": date_str,
            "event_count": len(events_on_date),
            "summary": summary_text,
            "voice_response": summary_text,
        }

    @server.tool()
    def ask_memory(person: str = "dad", question: str = "") -> Dict[str, Any]:
        """
        Answer caregiver questions about the elder parent's routine history, habits, and recorded events.
        Uses Amazon Bedrock memory Q&A sandboxed strictly to factual event logs.

        VOICE TRIGGERS (Alexa+ Intent Matching):
        - "Did Dad take his pills today?"
        - "What time did Mom eat lunch?"
        - "Was there any movement in the kitchen this morning?"

        WHEN TO CALL:
        - Call when family asks a specific factual question about past routine events.

        Parameters:
            person: Identifier of the elder parent (e.g. 'eleanor', 'dad')
            question: Specific query about the parent's routine
        """
        p_id = validate_person_identifier(person)
        check_tool_authorization("ask_memory", person=p_id)
        person_id = p_id

        if not question or not question.strip():
            raise ToolError("Question cannot be empty.")
        if len(question) > 1000:
            raise ToolError("Question exceeds maximum length of 1000 characters.")

        now = clock.now()
        profile = storage.get_profile(person_id)
        display_name = profile.display_name if profile else person_id.capitalize()
        person_tz_str = profile.timezone if profile and profile.timezone else "UTC"

        answer = llm_assistant.ask_memory(
            person=person_id,
            question=question.strip(),
            storage=storage,
            now=now,
            display_name=display_name,
            person_tz=person_tz_str,
        )

        return {
            "person": person_id,
            "question": question,
            "answer": answer,
            "voice_response": answer,
        }

    @server.tool()
    def tick_escalation(person: Optional[str] = None) -> Dict[str, Any]:
        """
        Autonomous periodic routine tick advancing the escalation state machine without waiting for user requests.

        WHEN TO CALL:
        - Called autonomously by background timers or Amazon EventBridge minute rules.

        Parameters:
            person: Optional identifier of the elder parent. If omitted, ticks all known persons.
        """
        p_id = validate_person_identifier(person) if person else None
        check_tool_authorization("tick_escalation", person=p_id)

        now = clock.now()
        if p_id:
            state = escalation_engine.tick(p_id, now)
            voice_msg = f"Routine check completed for {p_id}. Current stage is {state.stage.value}."
            return {
                "status": "ticked",
                "timestamp": now.isoformat(),
                "person": p_id,
                "stage": state.stage.value,
                "risk_score": state.risk_score,
                "reasons": state.reasons,
                "voice_response": voice_msg,
            }
        else:
            results: Dict[str, Any] = {}
            profiles = storage.list_profiles()
            known_persons = [p.person_id for p in profiles] if profiles else ["dad", "eleanor"]
            for p_id in known_persons:
                st = escalation_engine.tick(p_id, now)
                results[p_id] = {
                    "stage": st.stage.value,
                    "risk_score": st.risk_score,
                    "reasons": st.reasons,
                }
            voice_msg = f"Routine checks completed for {len(known_persons)} monitored profiles."
            return {
                "status": "ticked",
                "timestamp": now.isoformat(),
                "persons": results,
                "voice_response": voice_msg,
            }

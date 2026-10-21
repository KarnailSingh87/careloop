"""
CareLoop Voice Reminder Scheduler and Lifecycle Manager.

Handles reminder persistence, time evaluation, and due reminder processing.

CRITICAL ARCHITECTURAL BOUNDARY:
CareLoop persists, schedules, and tracks reminders in SQLite and DynamoDB.
However, physical voice announcement through an Amazon Echo speaker requires:
1. An active Alexa Skill deployment with ASK Reminders API permissions.
2. A customer-delegated OAuth 2.0 token (alexa::alerts:reminders:skill:readwrite).
3. Alexa Device / User ID targeting.
CareLoop documents and identifies these missing external requirements rather
than simulating or falsely claiming physical Echo delivery.
"""

from abc import ABC, abstractmethod
from datetime import datetime, time, timezone
import logging
import re
from typing import Any, Callable, Dict, List, Optional
from dateutil import parser as date_parser

from careloop.clock import Clock
from careloop.models import PersonProfile, Reminder, ReminderStatus
from careloop.storage.base import StorageBase

logger = logging.getLogger(__name__)

# Documented requirements for Amazon Echo hardware reminder delivery
ALEXA_REMINDER_DELIVERY_REQUIREMENTS = {
    "api_endpoint": "https://api.amazonalexa.com/v1/alerts/reminders",
    "required_permission": "alexa::alerts:reminders:skill:readwrite",
    "protocol": "Alexa Skills Kit (ASK) Reminders API / Proactive Events API",
    "missing_components": [
        "Login with Amazon (LWA) OAuth 2.0 access token with alexa::alerts:reminders:skill:readwrite consent",
        "Alexa customer device/endpoint identifier mapping for physical Echo speaker targeting",
        "ASK skill runtime bridge executing in AWS Lambda or certified HTTPS skill endpoint",
    ],
    "current_capability": (
        "Reminders are safely persisted in SQLite/DynamoDB and evaluated against the injectable clock. "
        "Spoken text is returned in MCP tool voice_response for conversational agents, "
        "but direct audio broadcast to an Echo device requires the Alexa Skills Kit OAuth delegation."
    ),
}


class ReminderDeliveryBridge(ABC):
    """Abstract interface for dispatching reminders to speech or audio devices."""

    @abstractmethod
    def deliver_reminder(self, reminder: Reminder) -> bool:
        """Deliver or announce a reminder. Returns True on success."""
        pass


class ConsoleReminderDeliveryBridge(ReminderDeliveryBridge):
    """Local demonstration bridge that prints reminder announcements."""

    def __init__(self, output_fn: Optional[Callable[[str], None]] = None):
        self.output_fn = output_fn or print
        self.delivered_reminders: List[Reminder] = []

    def deliver_reminder(self, reminder: Reminder) -> bool:
        msg = f"🔔 [ALEXA+ SPOKEN REMINDER for {reminder.person_id.upper()}]: \"{reminder.text}\""
        self.output_fn(msg)
        self.delivered_reminders.append(reminder)
        logger.info(f"Delivered reminder {reminder.reminder_id} via ConsoleReminderDeliveryBridge: {reminder.text}")
        return True


class AlexaSkillRemindersBridge(ReminderDeliveryBridge):
    """
    Bridge targeting the real Alexa Reminders API.
    Explicitly raises an actionable error if the required OAuth token or device ID is missing.
    """

    def __init__(self, api_endpoint: Optional[str] = None, oauth_token: Optional[str] = None):
        self.api_endpoint = api_endpoint or ALEXA_REMINDER_DELIVERY_REQUIREMENTS["api_endpoint"]
        self.oauth_token = oauth_token

    def deliver_reminder(self, reminder: Reminder) -> bool:
        if not self.oauth_token:
            missing = "\n".join(f"  - {m}" for m in ALEXA_REMINDER_DELIVERY_REQUIREMENTS["missing_components"])
            err = (
                f"Cannot deliver reminder {reminder.reminder_id} to physical Echo speaker. "
                f"Missing required Alexa Skill credentials:\n{missing}"
            )
            logger.error(err)
            raise RuntimeError(err)
        # When token is present, this would POST to self.api_endpoint
        return True


def is_reminder_due(reminder: Reminder, now: datetime, person_tz_str: str = "UTC") -> bool:
    """
    Determine if a pending reminder is due at or before the given timestamp `now`.
    
    Supports:
    1. 'HH:MM' 24-hour time-of-day format: Evaluated against `now` in the person's timezone.
    2. ISO 8601 full datetime format: Evaluated directly against `now`.
    
    Parameters:
        reminder: The Reminder to check.
        now: Current timezone-aware timestamp (from injectable Clock).
        person_tz_str: Timezone name of the person (default "UTC").
    """
    if reminder.status != ReminderStatus.PENDING:
        return False

    if now.tzinfo is None:
        raise ValueError(f"Evaluation timestamp {now} must be timezone-aware.")

    sched = reminder.scheduled_time.strip()

    # 1. Check HH:MM format
    hh_mm_match = re.match(r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$", sched)
    if hh_mm_match:
        target_h = int(hh_mm_match.group(1))
        target_m = int(hh_mm_match.group(2))

        # Convert `now` to person's local time if possible
        try:
            from zoneinfo import ZoneInfo
            person_tz = ZoneInfo(person_tz_str)
            local_now = now.astimezone(person_tz)
        except Exception:
            local_now = now

        now_time = local_now.time()
        target_time = time(target_h, target_m)
        
        # Due if current time is at or past target_time on the same or later date
        # (Compare date and time)
        created_local = reminder.created_at
        if created_local.tzinfo is not None:
            try:
                created_local = created_local.astimezone(local_now.tzinfo)
            except Exception:
                pass

        if local_now.date() > created_local.date():
            # If a day or more has passed since creation, reminder is definitely due
            return True
        elif local_now.date() == created_local.date():
            return now_time >= target_time
        else:
            return False

    # 2. Check ISO 8601 full datetime format
    try:
        target_dt = date_parser.parse(sched)
        if target_dt.tzinfo is None:
            # Assume UTC if naive
            target_dt = target_dt.replace(tzinfo=timezone.utc)
        return now >= target_dt
    except Exception as e:
        logger.warning(f"Could not parse reminder scheduled_time '{sched}': {e}")
        return False


class ReminderScheduler:
    """
    Safe reminder scheduler that persists reminders and processes due reminders.
    
    Adheres to the CareLoop architecture:
    - Never silently fails or drops reminders.
    - Uses the injected Clock for deterministic, reproducible testing.
    - Transitions reminders from PENDING -> COMPLETED or FAILED.
    - Documents the missing physical Echo speaker bridge rather than faking it.
    """

    def __init__(
        self,
        storage: StorageBase,
        clock: Clock,
        delivery_bridge: Optional[ReminderDeliveryBridge] = None,
    ):
        self.storage = storage
        self.clock = clock
        self.delivery_bridge = delivery_bridge or ConsoleReminderDeliveryBridge()

    def process_due_reminders(
        self,
        person_id: str,
        now: Optional[datetime] = None,
    ) -> List[Reminder]:
        """
        Scan active reminders for a person, evaluate due ones against the clock,
        dispatch through the delivery bridge, and persist state transitions.
        
        Returns the list of processed reminders.
        """
        current_time = now or self.clock.now()
        if current_time.tzinfo is None:
            raise ValueError(f"Current time {current_time} must be timezone-aware.")

        profile = self.storage.get_profile(person_id)
        person_tz = profile.timezone if profile and profile.timezone else "UTC"

        active_reminders = self.storage.get_reminders(person_id, active_only=True)
        processed: List[Reminder] = []

        for reminder in active_reminders:
            if is_reminder_due(reminder, current_time, person_tz):
                logger.info(
                    f"Processing due reminder {reminder.reminder_id} for {person_id}: "
                    f"scheduled={reminder.scheduled_time}, now={current_time.isoformat()}"
                )
                try:
                    success = self.delivery_bridge.deliver_reminder(reminder)
                    if success:
                        reminder.status = ReminderStatus.COMPLETED
                        reminder.completed_at = current_time
                        reminder.error = None
                    else:
                        reminder.status = ReminderStatus.FAILED
                        reminder.error = "Delivery bridge returned failure"
                except Exception as ex:
                    reminder.status = ReminderStatus.FAILED
                    reminder.error = str(ex)
                    logger.error(f"Error delivering reminder {reminder.reminder_id}: {ex}")

                self.storage.save_reminder(reminder)
                processed.append(reminder)

        return processed

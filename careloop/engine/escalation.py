"""
Persisted escalation state machine engine for CareLoop.

States:
  normal -> gentle_check_in -> repeat_check_in -> notify_family

Key Architectural Guarantees:
- Fully persisted and stateless: all state is retrieved from and committed to StorageBase.
- Timezone-aware: all operations require an explicit timezone-aware datetime from the injected clock.
- Separation of Notification Decision vs Delivery:
    * Reaching 'notify_family' creates a deterministic Alert with evidence-based reasons and
      stores it with notification_status='pending'.
    * Delivery is attempted separately, recording delivery failures without duplicating alerts.
    * Retrying delivers failed alerts without sending duplicate SMS/SNS messages to families.
- Idempotent Ticks: Repeated ticks on the same stage or timestamp never generate duplicate alerts
  or duplicate notification calls.
- Optimistic Concurrency Control: Concurrent ticks or stale background workers with outdated
  state versions are safely rejected via StaleStateError.
- Authoritative Resets: An elder confirming "I'm fine", calling confirm_ok, or any qualifying
  new routine event immediately resets state to NORMAL and marks active alerts as RESOLVED.
- Zero-Safety-Inference: Absence of events is never inferred as safety; if routines are missed,
  the state machine strictly escalates.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import uuid

from careloop.engine.baseline import BaselineEngine
from careloop.engine.risk import RiskEngine, RiskAssessment
from careloop.models import (
    Alert,
    AlertLevel,
    CheckinPrompt,
    CheckinStatus,
    EscalationStage,
    EscalationState,
    Event,
)
from careloop.storage.base import StorageBase, StaleStateError

logger = logging.getLogger(__name__)


class EscalationEngine:
    """Persisted escalation state machine."""

    def __init__(
        self,
        storage: StorageBase,
        risk_engine: Optional[RiskEngine] = None,
        baseline_engine: Optional[BaselineEngine] = None,
        notifier: Optional[Any] = None,
        gentle_timeout_seconds: float = 60.0,   # Default demo timeout: 60s
        repeat_timeout_seconds: float = 60.0,   # Default demo timeout: 60s
    ) -> None:
        self.storage = storage
        self.risk_engine = risk_engine or RiskEngine()
        self.baseline_engine = baseline_engine
        self.notifier = notifier
        self.gentle_timeout_seconds = gentle_timeout_seconds
        self.repeat_timeout_seconds = repeat_timeout_seconds

    def get_or_create_state(self, person_id: str, now: datetime) -> EscalationState:
        """Fetch persisted state from storage or initialize to 'normal'."""
        if now.tzinfo is None:
            raise ValueError(f"State timestamp {now} must be timezone-aware.")
        state = self.storage.get_escalation_state(person_id)
        if state is None:
            state = EscalationState(
                person_id=person_id,
                stage=EscalationStage.NORMAL,
                entered_at=now,
                last_updated=now,
                risk_score=0.0,
                reasons=["System initialized: nominal monitoring state."],
                event_references=[],
                notification_state="none",
                notification_id=None,
                version=1,
            )
            self.storage.save_escalation_state(state, check_version=False)
        return state

    def reset_to_normal(
        self,
        person_id: str,
        now: datetime,
        reason: str = "Routine event observed",
        event_id: Optional[str] = None,
    ) -> EscalationState:
        """
        Reset escalation state machine to 'normal'.
        Called when any qualifying new event is logged, when confirm_ok is called,
        or when the person responds 'I'm fine'.
        """
        if now.tzinfo is None:
            raise ValueError(f"Reset timestamp {now} must be timezone-aware.")

        existing = self.storage.get_escalation_state(person_id)
        next_ver = (existing.version + 1) if existing else 1

        state = EscalationState(
            person_id=person_id,
            stage=EscalationStage.NORMAL,
            entered_at=now,
            last_updated=now,
            risk_score=0.0,
            reasons=[f"Reset to normal: {reason}"],
            event_references=[event_id] if event_id else [],
            notification_state="none",
            notification_id=None,
            version=next_ver,
            metadata={"reset_reason": reason},
        )
        self.storage.save_escalation_state(state, check_version=False)

        # Resolve active alerts for this person upon safe confirmation/reset
        try:
            active_alerts = self.storage.get_alerts(person_id, active_only=True)
            for alert in active_alerts:
                alert.status = "RESOLVED"
                alert.metadata["resolved_at"] = now.isoformat()
                alert.metadata["resolved_reason"] = reason
                if event_id:
                    alert.metadata["resolved_by_event"] = event_id
                self.storage.save_alert(alert)
        except Exception as e:
            logger.warning(f"Could not resolve active alerts for {person_id}: {e}")

        logger.info(f"Escalation reset to NORMAL for {person_id}: {reason}")
        return state

    def reset_on_event(self, event: Event) -> EscalationState:
        """Reset escalation to normal when a qualifying new routine event arrives."""
        return self.reset_to_normal(
            person_id=event.person_id,
            now=event.timestamp,
            reason=f"Qualifying routine event observed: {event.event_type.value}",
            event_id=event.event_id,
        )

    def handle_voice_response(
        self,
        person_id: str,
        response_text: str,
        now: datetime,
    ) -> EscalationState:
        """
        Process speech response from elder parent.
        If response indicates "I'm fine" or affirmative confirmation, resets state to normal.
        """
        if now.tzinfo is None:
            raise ValueError(f"Voice response timestamp {now} must be timezone-aware.")
        cleaned = response_text.strip().lower()
        reset_phrases = [
            "i'm fine", "im fine", "fine", "yes", "i did", "i took it",
            "all good", "okay", "ok", "i am okay", "i'm okay", "alright"
        ]
        is_fine = any(phrase in cleaned for phrase in reset_phrases)

        if is_fine:
            return self.reset_to_normal(
                person_id=person_id,
                now=now,
                reason=f"Elder confirmed safe: '{response_text}'",
            )

        # Non-reset response recorded
        state = self.get_or_create_state(person_id, now)
        state.last_updated = now
        state.metadata["last_voice_response"] = response_text
        self.storage.save_escalation_state(state, check_version=True)
        return state

    def deliver_notification(
        self,
        alert: Alert,
        state: EscalationState,
        now: datetime,
    ) -> bool:
        """
        Attempt delivery of a previously decided alert to designated family contacts.
        Updates alert and state delivery status, recording failures for retry.
        Idempotent: if already delivered, returns True immediately without resending.
        """
        if alert.notification_status == "delivered" and state.notification_state == "delivered":
            logger.info(f"Alert {alert.alert_id} already delivered. Skipping duplicate delivery.")
            return True

        delivered = False
        err_msg = None

        if self.notifier:
            try:
                profile = self.storage.get_profile(state.person_id)
                contacts = profile.emergency_contacts if profile else None
                success = self.notifier.send_notification(
                    person_id=state.person_id,
                    severity="high",
                    message=alert.title,
                    reasons=alert.reasons,
                    contacts=contacts,
                )
                if success:
                    delivered = True
                else:
                    err_msg = "Notifier returned failure status (False)"
            except Exception as e:
                err_msg = str(e)
                logger.error(f"Notification delivery exception for {state.person_id}: {e}")
        else:
            # Default mock/simulated delivery when no notifier injected
            delivered = True

        if delivered:
            alert.notification_status = "delivered"
            alert.delivered_at = now
            alert.delivery_error = None
            self.storage.save_alert(alert)

            state.notification_state = "delivered"
            state.last_updated = now
            self.storage.save_escalation_state(state, check_version=True)
            logger.info(f"Delivered alert {alert.alert_id} to family for {state.person_id}")
            return True
        else:
            alert.notification_status = "failed"
            alert.delivery_error = err_msg
            alert.retry_count += 1
            self.storage.save_alert(alert)

            state.notification_state = "failed"
            state.last_updated = now
            self.storage.save_escalation_state(state, check_version=True)
            logger.warning(
                f"Delivery failed for alert {alert.alert_id} (person={state.person_id}, "
                f"retry_count={alert.retry_count}): {err_msg}"
            )
            return False

    def retry_failed_notifications(self, person_id: str, now: datetime) -> int:
        """
        Retry delivery of any pending or failed alerts for a person without duplicating delivered alerts.
        Returns the number of alerts successfully redelivered.
        """
        if now.tzinfo is None:
            raise ValueError(f"Retry timestamp {now} must be timezone-aware.")

        alerts = self.storage.get_alerts(person_id, active_only=False)
        failed_alerts = [
            a for a in alerts
            if a.notification_status in ("failed", "pending") and a.status == "ACTIVE"
        ]

        delivered_count = 0
        state = self.storage.get_escalation_state(person_id) or self.get_or_create_state(person_id, now)

        for alert in failed_alerts:
            if self.deliver_notification(alert, state, now):
                delivered_count += 1

        return delivered_count

    def tick(
        self,
        person_id: str,
        now: datetime,
        forced_risk: Optional[RiskAssessment] = None,
    ) -> EscalationState:
        """
        Advance the escalation state machine based on elapsed time and current routine risk.

        Transitions:
          normal -> gentle_check_in (when risk is medium or high)
          gentle_check_in -> repeat_check_in (when gentle_timeout expires)
          repeat_check_in -> notify_family (when repeat_timeout expires)
          notify_family -> stays until reset
        """
        if now.tzinfo is None:
            raise ValueError(f"Tick timestamp {now} must be timezone-aware.")
        state = self.get_or_create_state(person_id, now)

        # 1. Evaluate current routine risk
        events_today: List[Event] = []
        if forced_risk is not None:
            risk = forced_risk
        else:
            events_today = self.storage.get_events(person_id, limit=50)
            risk = self.risk_engine.evaluate_person_risk(
                person_id=person_id,
                now=now,
                baseline_engine=self.baseline_engine,
                events_today=events_today,
            )

        # Retain elevated risk assessment while escalated until an explicit reset occurs.
        # Absence of new events must never falsely infer safety or reset an active check-in to nominal.
        if state.stage != EscalationStage.NORMAL:
            if risk.score > state.risk_score:
                state.risk_score = risk.score
                state.reasons = risk.reasons
        else:
            state.risk_score = risk.score
            state.reasons = risk.reasons

        if events_today:
            state.event_references = [e.event_id for e in events_today[:10] if e.event_id]

        # 2. State machine evaluation
        if state.stage == EscalationStage.NORMAL:
            # If risk elevates to medium or high (score >= 0.3)
            if risk.level in ("medium", "high") or risk.score >= 0.3:
                state.stage = EscalationStage.GENTLE_CHECK_IN
                state.entered_at = now
                state.last_updated = now
                state.notification_state = "none"
                logger.info(
                    f"Escalation: NORMAL -> GENTLE_CHECK_IN for {person_id} "
                    f"(risk_level={risk.level}, score={risk.score})"
                )
            else:
                state.last_updated = now
            self.storage.save_escalation_state(state, check_version=True)
            return state

        elif state.stage == EscalationStage.GENTLE_CHECK_IN:
            elapsed = (now - state.entered_at).total_seconds()
            if elapsed >= self.gentle_timeout_seconds:
                state.stage = EscalationStage.REPEAT_CHECK_IN
                state.entered_at = now
                state.last_updated = now
                state.notification_state = "none"
                logger.info(
                    f"Escalation: GENTLE_CHECK_IN -> REPEAT_CHECK_IN for {person_id} "
                    f"after {elapsed:.1f}s timeout."
                )
            else:
                state.last_updated = now
            self.storage.save_escalation_state(state, check_version=True)
            return state

        elif state.stage == EscalationStage.REPEAT_CHECK_IN:
            elapsed = (now - state.entered_at).total_seconds()
            if elapsed >= self.repeat_timeout_seconds:
                state.stage = EscalationStage.NOTIFY_FAMILY
                state.entered_at = now
                state.last_updated = now
                state.notification_state = "pending"
                logger.warning(
                    f"Escalation: REPEAT_CHECK_IN -> NOTIFY_FAMILY for {person_id} "
                    f"after {elapsed:.1f}s timeout. Dispatched family alert!"
                )
                decision_id = str(uuid.uuid4())
                alert = Alert(
                    alert_id=str(uuid.uuid4()),
                    person_id=person_id,
                    level=AlertLevel.CRITICAL_ESCALATION,
                    created_at=now,
                    title=f"Elder Care Alert: {person_id.capitalize()} Unresponsive to Routine Check-Ins",
                    reasons=risk.reasons + [
                        f"Gentle voice check-in timed out ({self.gentle_timeout_seconds:.0f}s).",
                        f"Repeat voice check-in timed out ({self.repeat_timeout_seconds:.0f}s) with no response.",
                    ],
                    recommended_action="Contact elder parent by phone immediately or notify designated primary caregiver.",
                    status="ACTIVE",
                    notification_status="pending",
                    event_ids=state.event_references.copy(),
                    metadata={
                        "decision_id": decision_id,
                        "risk_score": risk.score,
                        "risk_level": risk.level,
                        "gentle_timeout_seconds": self.gentle_timeout_seconds,
                        "repeat_timeout_seconds": self.repeat_timeout_seconds,
                    },
                )
                state.notification_id = alert.alert_id

                # Persist decision and alert FIRST before attempting delivery
                self.storage.save_alert(alert)
                self.storage.save_escalation_state(state, check_version=True)

                # Attempt delivery
                self.deliver_notification(alert, state, now)
                return state
            else:
                state.last_updated = now
                self.storage.save_escalation_state(state, check_version=True)
                return state

        elif state.stage == EscalationStage.NOTIFY_FAMILY:
            state.last_updated = now
            # Idempotency check:
            if state.notification_state == "delivered":
                # Already delivered. Idempotent tick: do not create new alert or duplicate notifications.
                self.storage.save_escalation_state(state, check_version=True)
                return state
            elif state.notification_state in ("failed", "pending") and state.notification_id:
                # Retry delivery of the existing alert
                alerts = self.storage.get_alerts(person_id, active_only=False)
                existing_alert = next((a for a in alerts if a.alert_id == state.notification_id), None)
                if existing_alert:
                    self.deliver_notification(existing_alert, state, now)
                else:
                    self.storage.save_escalation_state(state, check_version=True)
                return state
            else:
                self.storage.save_escalation_state(state, check_version=True)
                return state

        return state

"""
Persisted escalation state machine engine for CareLoop.

States:
  normal -> gentle_check_in -> repeat_check_in -> notify_family

Rules:
- Server is stateless: all state is retrieved from and persisted to the StorageBase backend.
- tick(person, now) evaluates risk and advances state when stage timeouts expire.
- Any new event or the elder replying "I'm fine" resets escalation back to 'normal'.
- When reaching 'notify_family', a deterministic Alert with plain-English reasons is persisted.
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
from careloop.storage.base import StorageBase

logger = logging.getLogger(__name__)


class EscalationEngine:
    """Persisted escalation state machine."""

    def __init__(
        self,
        storage: StorageBase,
        risk_engine: Optional[RiskEngine] = None,
        baseline_engine: Optional[BaselineEngine] = None,
        gentle_timeout_seconds: float = 60.0,   # Default demo timeout: 60s
        repeat_timeout_seconds: float = 60.0,   # Default demo timeout: 60s
    ) -> None:
        self.storage = storage
        self.risk_engine = risk_engine or RiskEngine()
        self.baseline_engine = baseline_engine
        self.gentle_timeout_seconds = gentle_timeout_seconds
        self.repeat_timeout_seconds = repeat_timeout_seconds

    def get_or_create_state(self, person_id: str, now: datetime) -> EscalationState:
        """Fetch persisted state from storage or initialize to 'normal'."""
        state = self.storage.get_escalation_state(person_id)
        if state is None:
            state = EscalationState(
                person_id=person_id,
                stage=EscalationStage.NORMAL,
                entered_at=now,
                last_updated=now,
                risk_score=0.0,
                reasons=["System initialized: nominal monitoring state."],
            )
            self.storage.save_escalation_state(state)
        return state

    def reset_to_normal(
        self,
        person_id: str,
        now: datetime,
        reason: str = "Routine event observed",
    ) -> EscalationState:
        """
        Reset escalation state machine to 'normal'.
        Called when any new event is logged or when the person responds 'I'm fine'.
        """
        state = EscalationState(
            person_id=person_id,
            stage=EscalationStage.NORMAL,
            entered_at=now,
            last_updated=now,
            risk_score=0.0,
            reasons=[f"Reset to normal: {reason}"],
            metadata={"reset_reason": reason},
        )
        self.storage.save_escalation_state(state)
        logger.info(f"Escalation reset to NORMAL for {person_id}: {reason}")
        return state

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
        cleaned = response_text.strip().lower()
        reset_phrases = ["i'm fine", "im fine", "fine", "yes", "i did", "i took it", "all good", "okay", "ok"]
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
        self.storage.save_escalation_state(state)
        return state

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
        state = self.get_or_create_state(person_id, now)

        # 1. Evaluate current routine risk
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

        state.risk_score = risk.score
        state.reasons = risk.reasons

        # 2. State machine evaluation
        if state.stage == EscalationStage.NORMAL:
            # If risk elevates to medium or high (score >= 0.3)
            if risk.level in ("medium", "high") or risk.score >= 0.3:
                state.stage = EscalationStage.GENTLE_CHECK_IN
                state.entered_at = now
                state.last_updated = now
                logger.info(
                    f"Escalation: NORMAL -> GENTLE_CHECK_IN for {person_id} "
                    f"(risk_level={risk.level}, score={risk.score})"
                )
            else:
                state.last_updated = now

        elif state.stage == EscalationStage.GENTLE_CHECK_IN:
            elapsed = (now - state.entered_at).total_seconds()
            if elapsed >= self.gentle_timeout_seconds:
                state.stage = EscalationStage.REPEAT_CHECK_IN
                state.entered_at = now
                state.last_updated = now
                logger.info(
                    f"Escalation: GENTLE_CHECK_IN -> REPEAT_CHECK_IN for {person_id} "
                    f"after {elapsed:.1f}s timeout."
                )
            else:
                state.last_updated = now

        elif state.stage == EscalationStage.REPEAT_CHECK_IN:
            elapsed = (now - state.entered_at).total_seconds()
            if elapsed >= self.repeat_timeout_seconds:
                state.stage = EscalationStage.NOTIFY_FAMILY
                state.entered_at = now
                state.last_updated = now
                logger.warning(
                    f"Escalation: REPEAT_CHECK_IN -> NOTIFY_FAMILY for {person_id} "
                    f"after {elapsed:.1f}s timeout. Dispatched family alert!"
                )
                # Dispatch deterministic family Alert to storage
                alert = Alert(
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
                    metadata={"risk_score": risk.score, "risk_level": risk.level},
                )
                self.storage.save_alert(alert)
            else:
                state.last_updated = now

        elif state.stage == EscalationStage.NOTIFY_FAMILY:
            state.last_updated = now

        # Persist updated state to DB
        self.storage.save_escalation_state(state)
        return state

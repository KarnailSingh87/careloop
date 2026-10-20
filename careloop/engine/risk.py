"""
Deterministic risk evaluation engine for CareLoop.

Formula:
  risk = sum(weight_i * anomaly_i)
Weights:
  - medication_missed: 0.4
  - no_movement: 0.3
  - odd_hour_activity: 0.2
  - meal_missed: 0.2

Classification:
  - low: score < 0.3
  - medium: 0.3 <= score < 0.6
  - high: score >= 0.6

Zero LLM in the loop: alerts and risk levels are 100% deterministic code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from careloop.engine.baseline import BaselineEngine
from careloop.models import Event, EventType


@dataclass
class RiskAssessment:
    """Result of deterministic risk score calculation."""
    score: float
    level: str                       # 'low', 'medium', 'high'
    reasons: List[str] = field(default_factory=list)
    anomalies: Dict[str, bool] = field(default_factory=dict)


class RiskEngine:
    """Deterministic elder routine risk calculator."""

    WEIGHTS = {
        "medication_missed": 0.4,
        "no_movement": 0.3,
        "odd_hour_activity": 0.2,
        "meal_missed": 0.2,
    }

    def calculate_risk(
        self,
        medication_missed: bool = False,
        no_movement: bool = False,
        odd_hour_activity: bool = False,
        meal_missed: bool = False,
    ) -> RiskAssessment:
        """
        Compute deterministic weighted risk score and return plain-English reasons.
        """
        score = 0.0
        reasons: List[str] = []
        anomalies = {
            "medication_missed": bool(medication_missed),
            "no_movement": bool(no_movement),
            "odd_hour_activity": bool(odd_hour_activity),
            "meal_missed": bool(meal_missed),
        }

        if medication_missed:
            w = self.WEIGHTS["medication_missed"]
            score += w
            reasons.append(f"Medication missed past baseline grace window (weight: {w:.1f})")

        if no_movement:
            w = self.WEIGHTS["no_movement"]
            score += w
            reasons.append(f"Prolonged daytime inactivity / no movement detected (weight: {w:.1f})")

        if odd_hour_activity:
            w = self.WEIGHTS["odd_hour_activity"]
            score += w
            reasons.append(f"Uncharacteristic night-time activity detected during sleep hours (weight: {w:.1f})")

        if meal_missed:
            w = self.WEIGHTS["meal_missed"]
            score += w
            reasons.append(f"Expected meal routine not logged today (weight: {w:.1f})")

        score = round(score, 2)

        if score < 0.3:
            level = "low"
        elif score < 0.6:
            level = "medium"
        else:
            level = "high"

        if not reasons:
            reasons.append("All routines within nominal baseline thresholds.")

        return RiskAssessment(
            score=score,
            level=level,
            reasons=reasons,
            anomalies=anomalies,
        )

    def evaluate_person_risk(
        self,
        person_id: str,
        now: datetime,
        baseline_engine: Optional[BaselineEngine] = None,
        events_today: Optional[List[Event]] = None,
    ) -> RiskAssessment:
        """
        Inspect today's events and baseline learner to evaluate overall person risk.
        """
        events = events_today or []

        med_missed = False
        meal_missed = False
        if baseline_engine:
            med_missed = (baseline_engine.check_missed(person_id, "medication", now, events) == "missed")
            meal_missed = (baseline_engine.check_missed(person_id, "meal", now, events) == "missed")

        # Check daytime movement
        # If past morning waking hours (e.g. 09:00 UTC) and no movement in last 3 hours
        movement_events = [
            e for e in events
            if (e.event_type == EventType.MOVEMENT or getattr(e.event_type, "value", None) == "movement")
        ]
        no_movement = False
        if now.hour >= 9:
            if not movement_events:
                no_movement = True
            else:
                last_mov = max(e.timestamp for e in movement_events)
                if (now - last_mov).total_seconds() > 3 * 3600:
                    no_movement = True

        # Check odd hour activity (01:00 - 05:00 UTC/local)
        odd_hour = any(
            (1 <= e.timestamp.hour < 5)
            for e in events
            if e.event_type in (EventType.MOVEMENT, EventType.DOOR)
            or getattr(e.event_type, "value", None) in ("movement", "door")
        )

        return self.calculate_risk(
            medication_missed=med_missed,
            no_movement=no_movement,
            odd_hour_activity=odd_hour,
            meal_missed=meal_missed,
        )

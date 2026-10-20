"""
Statistical routine baseline learning and anomaly detection engine.

Implements:
- Circular EWMA (Exponentially Weighted Moving Average) for time-of-day in minutes (0-1440)
  with proper handling of midnight wraparound.
- Circular EWMA of variance to dynamically learn personal routine consistency.
- z-score anomaly detection (|z| > 2 flags anomalous event timing).
- Deterministic missed-event detection with configurable grace window
  (mu + k*sigma, with minimum 30-minute grace period to prevent false alarms).
- Cold-start rule: strictly suppresses all alerts with fewer than 5 observations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, date
import math
from typing import Any, Dict, List, Optional, Tuple

from careloop.models import Event, EventType


def circular_minute_difference(a: float, b: float) -> float:
    """
    Signed shortest angular distance from minute b to minute a on a 24-hour circle (1440 mins).
    Returns value in [-720.0, 720.0).
    Positive means 'a' is after 'b'.
    Negative means 'a' is before 'b'.
    """
    return ((a - b + 720.0) % 1440.0) - 720.0


@dataclass
class BaselineState:
    """Tracks EWMA statistics for a specific (person, event_type) pair."""
    person_id: str
    event_type: str
    count: int = 0
    mu_minutes: float = 0.0          # Range: [0.0, 1440.0)
    variance: float = 0.0            # Variance in minutes^2
    alpha: float = 0.2               # Smoothing factor
    last_event_time: Optional[datetime] = None

    @property
    def sigma(self) -> float:
        """Standard deviation in minutes (minimum floor of 1.0 to avoid division by zero)."""
        return max(1.0, math.sqrt(max(0.0, self.variance)))

    @property
    def expected_time_str(self) -> str:
        """Formatted HH:MM time string."""
        total_mins = int(round(self.mu_minutes)) % 1440
        return f"{total_mins // 60:02d}:{total_mins % 60:02d}"


@dataclass
class RoutineEvaluation:
    """Comprehensive evaluation result for routine status."""
    person_id: str
    event_type: str
    status: str                      # 'completed', 'pending', 'missed', 'cold_start'
    is_missed: bool
    is_anomaly: bool = False
    z_score: float = 0.0
    expected_time: Optional[str] = None
    grace_window_minutes: float = 30.0
    reasons: List[str] = field(default_factory=list)


class BaselineEngine:
    """
    Deterministic schedule baseline engine.
    
    Maintains circular EWMA of routine time and variance, and detects
    missed events or anomalous timings without any LLM in the loop.
    """

    def __init__(
        self,
        alpha: float = 0.2,
        k: float = 2.0,
        min_grace_minutes: float = 30.0,
        min_observations: int = 5,
    ) -> None:
        self.alpha = alpha
        self.k = k
        self.min_grace_minutes = min_grace_minutes
        self.min_observations = min_observations
        self.baselines: Dict[Tuple[str, str], BaselineState] = {}

    def _normalize_event_type(self, event_type: str) -> str:
        """Standardize event type aliases (e.g. 'pill' -> 'medication')."""
        t = event_type.strip().lower()
        if t in ("pill", "medication"):
            return "medication"
        return t

    def get_or_create_state(self, person: str, event_type: str) -> BaselineState:
        key = (person.strip().lower(), self._normalize_event_type(event_type))
        if key not in self.baselines:
            self.baselines[key] = BaselineState(
                person_id=key[0],
                event_type=key[1],
                alpha=self.alpha,
            )
        return self.baselines[key]

    def record_event(
        self,
        person: str,
        event_type: str,
        timestamp: datetime,
    ) -> Tuple[float, bool]:
        """
        Record a routine event observation and update EWMA statistics.

        Returns:
            (z_score, is_anomaly):
            - z_score: standard deviations from expected time
            - is_anomaly: True if |z| > 2.0 (always False during cold-start < 5 samples)
        """
        state = self.get_or_create_state(person, event_type)
        obs_minute = timestamp.hour * 60.0 + timestamp.minute + (timestamp.second / 60.0)

        # 1. Cold start / initial observation
        if state.count == 0:
            state.mu_minutes = obs_minute % 1440.0
            # Default initial variance ~15 minute std dev (225 min^2)
            state.variance = 225.0
            state.count = 1
            state.last_event_time = timestamp
            return 0.0, False

        # 2. Calculate signed circular difference from current mu to new observation
        diff = circular_minute_difference(obs_minute, state.mu_minutes)
        sigma = state.sigma
        z_score = diff / sigma

        # 3. Anomaly check: only evaluated after cold-start threshold
        is_anomaly = False
        if state.count >= self.min_observations:
            is_anomaly = abs(z_score) > 2.0

        # 4. Circular EWMA update
        # mu_new = (mu + alpha * diff) mod 1440
        state.mu_minutes = (state.mu_minutes + self.alpha * diff) % 1440.0

        # Variance EWMA update: var_new = (1 - alpha) * var + alpha * (diff^2)
        state.variance = (1.0 - self.alpha) * state.variance + self.alpha * (diff ** 2)
        state.count += 1
        state.last_event_time = timestamp

        return round(z_score, 2), is_anomaly

    def check_missed(
        self,
        person: str,
        event_type: str,
        current_time: datetime,
        events_today: Optional[List[Event]] = None,
    ) -> Optional[str]:
        """
        Check if a routine event is missed.

        Rules:
        - Cold-start (< 5 observations): returns None (no alert).
        - If an event of this type has already occurred today: returns None.
        - Grace window = mu + k*sigma (with minimum min_grace_minutes, default 30).
        - If current time passes the grace window with no event today: returns "missed".
        - Otherwise returns None.
        """
        eval_result = self.evaluate_routine(
            person=person,
            event_type=event_type,
            current_time=current_time,
            events_today=events_today,
        )
        return "missed" if eval_result.is_missed else None

    def evaluate_routine(
        self,
        person: str,
        event_type: str,
        current_time: datetime,
        events_today: Optional[List[Event]] = None,
    ) -> RoutineEvaluation:
        """
        Evaluate full routine status and produce deterministic audit reasons.
        """
        norm_type = self._normalize_event_type(event_type)
        key = (person.strip().lower(), norm_type)
        state = self.baselines.get(key)

        # Cold start check
        if state is None or state.count < self.min_observations:
            count = 0 if state is None else state.count
            return RoutineEvaluation(
                person_id=person,
                event_type=norm_type,
                status="cold_start",
                is_missed=False,
                is_anomaly=False,
                reasons=[
                    f"Cold start active: {count}/{self.min_observations} observations logged. Suppressing alerts."
                ],
            )

        # Check if event was already completed today
        if events_today:
            for ev in events_today:
                ev_type_norm = self._normalize_event_type(
                    ev.event_type.value if hasattr(ev.event_type, "value") else str(ev.event_type)
                )
                if ev_type_norm == norm_type:
                    return RoutineEvaluation(
                        person_id=person,
                        event_type=norm_type,
                        status="completed",
                        is_missed=False,
                        expected_time=state.expected_time_str,
                        reasons=[
                            f"Event '{norm_type}' was logged at {ev.timestamp.strftime('%H:%M')} UTC today."
                        ],
                    )

        # Calculate grace window
        # grace_margin = max(k * sigma, min_grace_minutes)
        grace_margin = max(self.k * state.sigma, self.min_grace_minutes)
        current_minute = current_time.hour * 60.0 + current_time.minute + (current_time.second / 60.0)

        # Difference in time from expected mu to current time
        diff_from_mu = circular_minute_difference(current_minute, state.mu_minutes)

        window_end_min = (state.mu_minutes + grace_margin) % 1440.0
        window_end_str = f"{int(window_end_min // 60):02d}:{int(window_end_min % 60):02d}"

        # If current time is after expected time and past the grace margin
        if diff_from_mu > grace_margin:
            minutes_overdue = int(round(diff_from_mu - grace_margin))
            return RoutineEvaluation(
                person_id=person,
                event_type=norm_type,
                status="missed",
                is_missed=True,
                expected_time=state.expected_time_str,
                grace_window_minutes=round(grace_margin, 1),
                reasons=[
                    f"Expected '{norm_type}' around {state.expected_time_str} UTC (sigma={state.sigma:.1f}m).",
                    f"Grace window ended at {window_end_str} UTC (+{grace_margin:.0f}m grace).",
                    f"Current time is {current_time.strftime('%H:%M')} UTC ({minutes_overdue}m past grace window) with no event recorded today.",
                ],
            )

        return RoutineEvaluation(
            person_id=person,
            event_type=norm_type,
            status="pending",
            is_missed=False,
            expected_time=state.expected_time_str,
            grace_window_minutes=round(grace_margin, 1),
            reasons=[
                f"Within normal schedule window for '{norm_type}'. Expected at {state.expected_time_str} UTC (grace window until {window_end_str} UTC)."
            ],
        )

"""
Statistical routine baseline learning and anomaly detection engine.

Implements:
- Circular EWMA (Exponentially Weighted Moving Average) for time-of-day in minutes (0-1440)
  with proper handling of midnight wraparound.
- Circular EWMA of variance to dynamically learn personal routine consistency.
- Robust Winsorized updates: extreme outliers (|z| > 3) are clamped during baseline
  updates so isolated emergencies do not permanently distort the learned routine.
- Configurable timezones: timestamps are converted to each person's configured timezone
  (e.g., America/New_York) to maintain consistent daily schedules across Daylight Saving Time.
- Deduplication: rapid successive events (<60s) or duplicate event IDs are rejected from
  contaminating baseline sample count and variance.
- Out-of-order handling: events arriving with historical timestamps are processed safely
  without corrupting sequential moving averages.
- Cold-start rule: strictly suppresses all alerts with fewer than 5 observations.
- Configurable minimum grace window (defaults to 30 minutes).
- Deterministic missed-event detection: an event is flagged as missed ONLY after its
  grace window has expired and no qualifying event occurred during today's routine window.
- Statistical calibration notice: for small sample sizes (N < 20), sample variance is an
  empirical estimate subject to sampling noise; z-score thresholds are operational screening
  heuristics rather than exact calibrated Gaussian probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, date
import logging
import math
from typing import Any, Dict, List, Optional, Tuple, Union
from zoneinfo import ZoneInfo

from careloop.models import Event, EventType, LearnedBaseline
from careloop.storage.base import StorageBase

logger = logging.getLogger(__name__)


def validate_and_localize(
    dt: datetime,
    target_tz: Union[str, ZoneInfo] = "UTC",
) -> datetime:
    """
    Validate that dt is timezone-aware and convert to target_tz.
    Raises ValueError if dt is naive to prevent silent mixing of local time and UTC.
    """
    if dt.tzinfo is None:
        raise ValueError(
            f"Timestamp {dt} is naive. All timestamps in CareLoop must be timezone-aware."
        )
    if isinstance(target_tz, str):
        try:
            tz = ZoneInfo(target_tz)
        except Exception:
            tz = timezone.utc
    else:
        tz = target_tz
    return dt.astimezone(tz)


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
    """Tracks circular EWMA statistics for a specific (person, event_type) pair."""
    person_id: str
    event_type: str
    count: int = 0
    mu_minutes: float = 0.0          # Range: [0.0, 1440.0) in person's local time
    variance: float = 0.0            # Variance in minutes^2
    alpha: float = 0.2               # Smoothing factor
    last_event_time: Optional[datetime] = None
    last_event_id: Optional[str] = None
    timezone_name: str = "UTC"

    @property
    def sigma(self) -> float:
        """
        Standard deviation in minutes.
        A floor of 5.0 minutes prevents division-by-zero and unrealistically narrow windows.
        """
        return max(5.0, math.sqrt(max(0.0, self.variance)))

    @property
    def expected_time_str(self) -> str:
        """Formatted HH:MM time string in local time."""
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
        default_timezone: str = "UTC",
        person_timezones: Optional[Dict[str, str]] = None,
    ) -> None:
        self.alpha = alpha
        self.k = k
        self.min_grace_minutes = min_grace_minutes
        self.min_observations = min_observations
        self.default_timezone = default_timezone
        self.person_timezones: Dict[str, str] = {
            k.strip().lower(): v for k, v in (person_timezones or {}).items()
        }
        self.baselines: Dict[Tuple[str, str], BaselineState] = {}

    def set_person_timezone(self, person: str, tz_name: str) -> None:
        """Configure the timezone for a specific person profile."""
        self.person_timezones[person.strip().lower()] = tz_name

    def get_person_timezone_name(self, person: str) -> str:
        """Return the timezone string for a person (e.g. 'America/New_York')."""
        return self.person_timezones.get(person.strip().lower(), self.default_timezone)

    def get_person_timezone(self, person: str) -> ZoneInfo:
        """Return ZoneInfo object for person's configured timezone."""
        tz_name = self.get_person_timezone_name(person)
        try:
            return ZoneInfo(tz_name)
        except Exception:
            logger.warning(f"Invalid timezone '{tz_name}' for person '{person}'. Falling back to UTC.")
            return ZoneInfo("UTC")

    def _to_person_local(self, person: str, dt: datetime) -> datetime:
        """Convert a timezone-aware timestamp into the person's local timezone."""
        return validate_and_localize(dt, self.get_person_timezone(person))

    def _normalize_event_type(self, event_type: str) -> str:
        """Standardize event type aliases (e.g. 'pill' -> 'medication')."""
        t = event_type.strip().lower()
        if t in ("pill", "medication"):
            return "medication"
        return t

    def get_or_create_state(self, person: str, event_type: str) -> BaselineState:
        norm_person = person.strip().lower()
        norm_type = self._normalize_event_type(event_type)
        key = (norm_person, norm_type)
        if key not in self.baselines:
            self.baselines[key] = BaselineState(
                person_id=norm_person,
                event_type=norm_type,
                alpha=self.alpha,
                timezone_name=self.get_person_timezone_name(person),
            )
        return self.baselines[key]

    def record_event(
        self,
        person: str,
        event_type: str,
        timestamp: datetime,
        event_id: Optional[str] = None,
    ) -> Tuple[float, bool]:
        """
        Record a routine event observation and update EWMA statistics.

        Rules:
        1. Timestamps must be timezone-aware; converted to person's local time.
        2. Duplicate events (identical event_id or logged < 60s from last event) are ignored.
        3. Out-of-order events (timestamp earlier than last_event_time) compute z-score safely
           without corrupting the sequential EWMA state.
        4. Cold-start (< 5 observations): is_anomaly is ALWAYS False.
        5. Extreme outliers (|z| > 3.0) are clamped (Winsorized) during EWMA update to
           prevent isolated emergencies from destroying the learned routine.

        Returns:
            (z_score, is_anomaly):
            - z_score: standard deviations from expected time
            - is_anomaly: True if |z| > 2.0 (only when count >= min_observations)
        """
        local_dt = self._to_person_local(person, timestamp)
        state = self.get_or_create_state(person, event_type)

        # 1. Deduplication check
        if event_id and state.last_event_id and event_id == state.last_event_id:
            logger.debug(f"Ignoring duplicate event_id={event_id} for {person}:{event_type}")
            return 0.0, False

        if state.last_event_time is not None:
            delta_sec = abs((timestamp - state.last_event_time).total_seconds())
            if delta_sec < 60.0:
                logger.debug(f"Ignoring duplicate event for {person}:{event_type} within {delta_sec:.1f}s")
                return 0.0, False

        obs_minute = local_dt.hour * 60.0 + local_dt.minute + (local_dt.second / 60.0)

        # 2. Cold-start initial observation
        if state.count == 0:
            state.mu_minutes = obs_minute % 1440.0
            state.variance = 225.0  # Initial ~15 minute std dev
            state.count = 1
            state.last_event_time = timestamp
            state.last_event_id = event_id
            return 0.0, False

        # 3. Out-of-order timestamp handling
        if state.last_event_time is not None and timestamp < state.last_event_time:
            diff = circular_minute_difference(obs_minute, state.mu_minutes)
            z_score = diff / state.sigma
            is_anomaly = (state.count >= self.min_observations) and (abs(z_score) > self.k)
            logger.info(
                f"Processed out-of-order event for {person}:{event_type} "
                f"(ts={timestamp.isoformat()}, last={state.last_event_time.isoformat()})"
            )
            return round(z_score, 2), is_anomaly

        # 4. Standard observation: circular difference from mu
        diff = circular_minute_difference(obs_minute, state.mu_minutes)
        sigma = state.sigma
        z_score = diff / sigma

        # Anomaly check: only evaluated after cold-start threshold
        is_anomaly = False
        if state.count >= self.min_observations:
            is_anomaly = abs(z_score) > self.k

        # 5. Robust Winsorized EWMA update
        # If extreme outlier (|z| > 3), clamp the deviation to 3*sigma to protect baseline
        if state.count >= self.min_observations and abs(z_score) > 3.0:
            effective_diff = max(-3.0 * sigma, min(3.0 * sigma, diff))
        else:
            effective_diff = diff

        state.mu_minutes = (state.mu_minutes + self.alpha * effective_diff) % 1440.0
        state.variance = (1.0 - self.alpha) * state.variance + self.alpha * (effective_diff ** 2)
        state.count += 1
        state.last_event_time = timestamp
        state.last_event_id = event_id

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
        current_local = self._to_person_local(person, current_time)
        norm_type = self._normalize_event_type(event_type)
        key = (person.strip().lower(), norm_type)
        state = self.baselines.get(key)
        tz_name = self.get_person_timezone_name(person)

        # 1. Cold start check
        if state is None or state.count < self.min_observations:
            count = 0 if state is None else state.count
            return RoutineEvaluation(
                person_id=person,
                event_type=norm_type,
                status="cold_start",
                is_missed=False,
                is_anomaly=False,
                reasons=[
                    f"Cold start active: {count}/{self.min_observations} observations logged for {person}. Suppressing alerts."
                ],
            )

        # 2. Calculate grace window
        grace_margin = max(self.k * state.sigma, self.min_grace_minutes)

        # 3. Check if qualifying event was completed today in local calendar time
        if events_today:
            for ev in events_today:
                ev_type_norm = self._normalize_event_type(
                    ev.event_type.value if hasattr(ev.event_type, "value") else str(ev.event_type)
                )
                if ev_type_norm == norm_type:
                    ev_local = self._to_person_local(person, ev.timestamp)
                    # Must be from the same local calendar day
                    if ev_local.date() == current_local.date():
                        ev_minute = ev_local.hour * 60.0 + ev_local.minute + (ev_local.second / 60.0)
                        dist = abs(circular_minute_difference(ev_minute, state.mu_minutes))
                        # Qualifies if within 4 hours (240m) of expected schedule or within grace margin + 60m
                        if dist <= max(grace_margin + 60.0, 240.0):
                            return RoutineEvaluation(
                                person_id=person,
                                event_type=norm_type,
                                status="completed",
                                is_missed=False,
                                expected_time=state.expected_time_str,
                                reasons=[
                                    f"Event '{norm_type}' was logged at {ev_local.strftime('%H:%M')} {tz_name} today."
                                ],
                            )

        # 4. Check whether current time is past grace window
        current_minute = current_local.hour * 60.0 + current_local.minute + (current_local.second / 60.0)
        diff_from_mu = circular_minute_difference(current_minute, state.mu_minutes)

        window_end_min = (state.mu_minutes + grace_margin) % 1440.0
        window_end_str = f"{int(window_end_min // 60):02d}:{int(window_end_min % 60):02d}"

        # If current time is after expected time and past the grace margin (and within 12 hours)
        if diff_from_mu > grace_margin and diff_from_mu < 720.0:
            minutes_overdue = int(round(diff_from_mu - grace_margin))
            return RoutineEvaluation(
                person_id=person,
                event_type=norm_type,
                status="missed",
                is_missed=True,
                expected_time=state.expected_time_str,
                grace_window_minutes=round(grace_margin, 1),
                reasons=[
                    f"Expected '{norm_type}' around {state.expected_time_str} {tz_name} (sigma={state.sigma:.1f}m).",
                    f"Grace window ended at {window_end_str} {tz_name} (+{grace_margin:.0f}m grace).",
                    f"Current time is {current_local.strftime('%H:%M')} {tz_name} ({minutes_overdue}m past grace window) with no event recorded today.",
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
                f"Within normal schedule window for '{norm_type}'. Expected at {state.expected_time_str} {tz_name} (grace window until {window_end_str} {tz_name})."
            ],
        )

    def load_from_storage(
        self,
        storage: Any,
        person_ids: Optional[List[str]] = None,
        limit_per_person: int = 500,
    ) -> int:
        """
        Replay historical events from storage to initialize baseline EWMA states.
        Avoids cold start if historical observations already exist in the database.
        """
        # Synchronize person timezones if storage has profiles
        if storage and hasattr(storage, "list_profiles"):
            try:
                profiles = storage.list_profiles()
                for p in profiles:
                    if getattr(p, "timezone", None):
                        self.set_person_timezone(p.person_id, p.timezone)
            except Exception as e:
                logger.debug(f"Could not load profiles for timezone sync: {e}")

        if person_ids is None:
            profiles = getattr(storage, "list_profiles", lambda: [])()
            if profiles:
                person_ids = [p.person_id for p in profiles]
            else:
                person_ids = ["eleanor", "dad"]

        total_loaded = 0
        for pid in person_ids:
            events = storage.get_events(pid, limit=limit_per_person)
            # Replay events in chronological order
            events_sorted = sorted(events, key=lambda e: e.timestamp)
            for ev in events_sorted:
                ev_type = ev.event_type.value if hasattr(ev.event_type, "value") else str(ev.event_type)
                self.record_event(pid, ev_type, ev.timestamp, event_id=getattr(ev, "event_id", None))
                total_loaded += 1
        return total_loaded

    def persist_baselines(self, storage: StorageBase) -> int:
        """
        Persist all in-memory learned baseline states to storage.
        """
        count = 0
        now = datetime.now(timezone.utc)
        for (pid, rtype), state in self.baselines.items():
            baseline = LearnedBaseline(
                person_id=pid,
                routine_type=rtype,
                sample_count=state.count,
                mean_time_minutes=round(state.mu_minutes, 2),
                std_dev_minutes=round(state.sigma, 2),
                earliest_time=state.expected_time_str,
                latest_time=state.expected_time_str,
                confidence_score=round(min(1.0, state.count / 20.0), 2),
                last_updated=state.last_event_time or now,
            )
            storage.save_baseline(baseline)
            count += 1
        return count


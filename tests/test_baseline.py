"""
Unit tests for CareLoop statistical baseline and anomaly detection engine.

Tests:
1. Cold start: With fewer than 5 observations, don't flag anything.
2. Normal days: Routine events logged within normal variance trigger no alert or anomaly.
3. One late lunch: Event logged slightly late within grace window or |z| <= 2 does not alert.
4. Missed pill: Once baseline is learned, clock passing grace window with no pill returns 'missed'.
5. Midnight wraparound: Routines crossing 00:00 calculate EWMA and variance accurately.
"""

from datetime import datetime, timezone, timedelta
import pytest

from careloop.clock import SimulatedClock
from careloop.engine.baseline import BaselineEngine, circular_minute_difference
from careloop.models import Event, EventType


def test_circular_minute_difference():
    # Regular daytime
    assert circular_minute_difference(510, 480) == 30.0    # 08:30 is 30m after 08:00
    assert circular_minute_difference(480, 510) == -30.0   # 08:00 is 30m before 08:30

    # Crossing midnight
    # 00:10 (10 min) vs 23:50 (1430 min): 00:10 is 20m after 23:50
    assert circular_minute_difference(10, 1430) == 20.0
    # 23:50 (1430 min) vs 00:10 (10 min): 23:50 is 20m before 00:10
    assert circular_minute_difference(1430, 10) == -20.0


def test_cold_start():
    """
    A cold-start rule: with fewer than 5 observations, don't flag anything.
    """
    clock = SimulatedClock(datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc))
    engine = BaselineEngine(min_observations=5)

    # Day 1: First observation at 08:30 (510 min)
    clock.set_time(datetime(2026, 10, 20, 8, 30, 0, tzinfo=timezone.utc))
    z, is_anomaly = engine.record_event("eleanor", "medication", clock.now())
    assert not is_anomaly
    assert z == 0.0

    # Day 2: Observation at 08:32
    clock.advance(timedelta(days=1, minutes=2))
    z, is_anomaly = engine.record_event("eleanor", "medication", clock.now())
    assert not is_anomaly

    # Day 3: Observation at an unusual time (e.g. 14:00 - 5.5 hours late)
    # Cold start should still suppress anomaly!
    clock.set_time(datetime(2026, 10, 22, 14, 0, 0, tzinfo=timezone.utc))
    z, is_anomaly = engine.record_event("eleanor", "medication", clock.now())
    assert not is_anomaly, "Cold start must not flag anomaly with count < 5"

    # Day 4: Check missed event late in the day (10:30 UTC) with no event
    # Cold start rule: don't flag anything!
    clock.set_time(datetime(2026, 10, 23, 10, 30, 0, tzinfo=timezone.utc))
    result = engine.check_missed("eleanor", "medication", clock.now(), events_today=[])
    assert result is None, "Cold start must not flag missed event with count < 5"

    eval_result = engine.evaluate_routine("eleanor", "medication", clock.now(), events_today=[])
    assert eval_result.status == "cold_start"
    assert not eval_result.is_missed


def test_normal_days():
    """
    Test 7 consecutive normal days of morning medication.
    Baseline converges, variance stays low, and no anomalies or missed events are flagged.
    """
    clock = SimulatedClock(datetime(2026, 10, 10, 8, 0, 0, tzinfo=timezone.utc))
    engine = BaselineEngine(min_observations=5)

    # Feed 7 days around 08:30 (jitter +- 3 mins)
    jitters = [0, 2, -2, 1, -1, 0, 2]
    for i, j in enumerate(jitters):
        day_time = datetime(2026, 10, 10 + i, 8, 30 + j, 0, tzinfo=timezone.utc)
        clock.set_time(day_time)
        z, is_anomaly = engine.record_event("eleanor", "medication", clock.now())
        assert not is_anomaly, f"Normal day {i+1} flagged unexpected anomaly (z={z})"

    state = engine.get_or_create_state("eleanor", "medication")
    assert state.count == 7
    # mu should be ~08:30 (around 510 minutes)
    assert 508.0 <= state.mu_minutes <= 512.0
    # sigma should be small
    assert state.sigma < 15.0

    # On Day 8 at 08:31, event occurs as normal
    clock.set_time(datetime(2026, 10, 18, 8, 31, 0, tzinfo=timezone.utc))
    z, is_anomaly = engine.record_event("eleanor", "medication", clock.now())
    assert not is_anomaly
    assert abs(z) < 1.0


def test_late_lunch_should_not_alert():
    """
    A person normally eats lunch around 12:30.
    One day they eat late at 12:45.
    This should NOT alert:
    1. At 12:45, it is within the 30-minute minimum grace window (window ends 13:00).
    2. The z-score is ~1.0-1.5, well below the |z| > 2 anomaly threshold.
    3. After eating, check_missed recognizes the lunch was completed.
    """
    clock = SimulatedClock(datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc))
    engine = BaselineEngine(min_observations=5)

    # Establish 6 days of lunch around 12:30 (12:28, 12:32, 12:30, 12:35, 12:25, 12:30)
    lunch_minutes = [28, 32, 30, 35, 25, 30]
    for day, m in enumerate(lunch_minutes):
        lunch_time = datetime(2026, 10, 10 + day, 12, m, 0, tzinfo=timezone.utc)
        clock.set_time(lunch_time)
        engine.record_event("eleanor", "meal", clock.now())

    state = engine.get_or_create_state("eleanor", "meal")
    assert state.count == 6
    assert abs(state.mu_minutes - 750.0) < 5.0

    # Day 7: At 12:44, lunch has not been logged yet
    current_time = datetime(2026, 10, 16, 12, 44, 0, tzinfo=timezone.utc)
    clock.set_time(current_time)

    # Check: 12:44 is only ~15 mins past mu=12:29.
    # Minimum grace window is 30 mins (window ends ~12:59).
    # Must NOT return 'missed'!
    res_before = engine.check_missed("eleanor", "meal", clock.now(), events_today=[])
    assert res_before is None, "12:44 is inside the grace window and must not trigger missed alert"

    # Now Eleanor eats late lunch at 12:45 and logs it
    clock.set_time(datetime(2026, 10, 16, 12, 45, 0, tzinfo=timezone.utc))
    z, is_anomaly = engine.record_event("eleanor", "meal", clock.now())

    # z-score: ~1.7 <= 2.0 -> no anomaly flagged!
    assert not is_anomaly, f"Late lunch should not be flagged as anomaly (z={z})"
    assert abs(z) <= 2.0

    # Later at 13:30 (past the grace window), verify check_missed does NOT alert
    # because lunch was completed today
    clock.set_time(datetime(2026, 10, 16, 13, 30, 0, tzinfo=timezone.utc))
    todays_event = Event(
        person_id="eleanor",
        event_type=EventType.MEAL,
        timestamp=datetime(2026, 10, 16, 12, 48, 0, tzinfo=timezone.utc),
    )
    res_after = engine.check_missed("eleanor", "meal", clock.now(), events_today=[todays_event])
    assert res_after is None, "Completed lunch must not alert"


def test_missed_pill_should_alert():
    """
    Morning pill is expected around 08:30 (510 minutes).
    Grace window = mu + max(2*sigma, 30) = 09:00.
    If current time passes the window with no event today, return 'missed'.
    """
    clock = SimulatedClock(datetime(2026, 10, 10, 8, 0, 0, tzinfo=timezone.utc))
    engine = BaselineEngine(min_observations=5)

    # Establish 6 days of morning pills at 08:30
    for day in range(6):
        med_time = datetime(2026, 10, 10 + day, 8, 30, 0, tzinfo=timezone.utc)
        clock.set_time(med_time)
        engine.record_event("eleanor", "medication", clock.now())

    state = engine.get_or_create_state("eleanor", "medication")
    assert state.count == 6

    # Day 7: Morning arrives
    # At 08:45: 15 min after expected time, still inside grace window (until 09:00)
    clock.set_time(datetime(2026, 10, 16, 8, 45, 0, tzinfo=timezone.utc))
    res_inside = engine.check_missed("eleanor", "medication", clock.now(), events_today=[])
    assert res_inside is None, "Should not alert while inside grace window"

    # Clock advances to 09:30: 30 minutes past the grace window with NO pill logged
    clock.set_time(datetime(2026, 10, 16, 9, 30, 0, tzinfo=timezone.utc))
    res_missed = engine.check_missed("eleanor", "medication", clock.now(), events_today=[])
    assert res_missed == "missed", "Must return 'missed' once past grace window"

    # Check detailed evaluation reasons
    eval_res = engine.evaluate_routine("eleanor", "medication", clock.now(), events_today=[])
    assert eval_res.is_missed is True
    assert eval_res.status == "missed"
    assert len(eval_res.reasons) >= 2
    # Verify human-readable explanation
    assert "Expected 'medication' around 08:30 UTC" in eval_res.reasons[0]
    assert "with no event recorded today" in eval_res.reasons[2]


def test_midnight_wraparound():
    """
    Test evening routine that hovers around midnight (e.g. 23:55).
    Verifies that circular EWMA correctly wraps across 00:00 without variance explosion.
    """
    clock = SimulatedClock(datetime(2026, 10, 10, 23, 50, 0, tzinfo=timezone.utc))
    engine = BaselineEngine(min_observations=5)

    # Routine times oscillating around midnight:
    # 23:55 (1435m), 00:05 (5m), 23:50 (1430m), 00:02 (2m), 23:58 (1438m), 00:01 (1m)
    times = [
        datetime(2026, 10, 10, 23, 55, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 12, 0, 5, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 12, 23, 50, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 14, 0, 2, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 14, 23, 58, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 16, 0, 1, 0, tzinfo=timezone.utc),
    ]

    for t in times:
        clock.set_time(t)
        engine.record_event("eleanor", "door", clock.now())

    state = engine.get_or_create_state("eleanor", "door")
    assert state.count == 6
    # mu should be very close to midnight (either ~1437 or ~00:01)
    assert state.mu_minutes > 1420.0 or state.mu_minutes < 20.0
    # Standard deviation should remain low (~8-15 min) despite crossing 00:00
    assert state.sigma < 20.0


def test_z_score_anomaly_detection():
    """
    Verify that once calibrated, an event occurring with |z| > 2 is flagged as an anomaly.
    """
    clock = SimulatedClock(datetime(2026, 10, 10, 8, 30, 0, tzinfo=timezone.utc))
    engine = BaselineEngine(min_observations=5)

    # Train 6 observations tightly clustered at 08:30 (sigma ~ 5-10m)
    for day in range(6):
        med_time = datetime(2026, 10, 10 + day, 8, 30, 0, tzinfo=timezone.utc)
        clock.set_time(med_time)
        engine.record_event("eleanor", "medication", clock.now())

    # Now pill is taken at 11:30 (3 hours late!)
    clock.set_time(datetime(2026, 10, 16, 11, 30, 0, tzinfo=timezone.utc))
    z, is_anomaly = engine.record_event("eleanor", "medication", clock.now())

    assert is_anomaly is True, f"3 hours late should be flagged as anomaly (z={z})"
    assert z > 2.0

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


def test_event_arriving_after_missed_event_alert():
    """
    Verify:
    1. At 09:30, clock passing grace window with no event triggers 'missed'.
    2. At 09:45, elder takes medication late.
    3. Once recorded, evaluate_routine recognizes event was completed today.
    4. A late event is NOT counted as both an anomaly and a missed event at the same time.
    """
    clock = SimulatedClock(datetime(2026, 10, 10, 8, 30, 0, tzinfo=timezone.utc))
    engine = BaselineEngine(min_observations=5)

    # 1. Calibrate 6 days of medication around 08:30
    for day in range(6):
        clock.set_time(datetime(2026, 10, 10 + day, 8, 30, 0, tzinfo=timezone.utc))
        engine.record_event("eleanor", "medication", clock.now())

    # 2. Day 7 at 09:30: Grace window expired, no event logged today -> MISSED
    clock.set_time(datetime(2026, 10, 16, 9, 30, 0, tzinfo=timezone.utc))
    res_missed = engine.check_missed("eleanor", "medication", clock.now(), events_today=[])
    assert res_missed == "missed"

    # 3. Elder takes medication late at 09:45 and logs it
    clock.set_time(datetime(2026, 10, 16, 9, 45, 0, tzinfo=timezone.utc))
    z, is_anomaly = engine.record_event("eleanor", "medication", clock.now())

    late_event = Event(
        person_id="eleanor",
        event_type=EventType.PILL,
        timestamp=clock.now(),
        metadata={"late": True},
    )

    # 4. Re-evaluate with today's completed event
    eval_after = engine.evaluate_routine("eleanor", "medication", clock.now(), events_today=[late_event])
    assert eval_after.status == "completed"
    assert eval_after.is_missed is False, "A logged late event must clear the missed status"

    # Verify check_missed returns None
    assert engine.check_missed("eleanor", "medication", clock.now(), events_today=[late_event]) is None


def test_duplicate_and_out_of_order_events():
    """
    Verify:
    1. Rapid successive events (<60s) or identical event IDs are deduplicated.
    2. Out-of-order events (timestamp earlier than last_event_time) do not corrupt EWMA state.
    """
    clock = SimulatedClock(datetime(2026, 10, 10, 8, 30, 0, tzinfo=timezone.utc))
    engine = BaselineEngine(min_observations=5)

    # Day 1: Log initial observation with event_id
    t1 = datetime(2026, 10, 10, 8, 30, 0, tzinfo=timezone.utc)
    engine.record_event("eleanor", "medication", t1, event_id="ev_001")
    state = engine.get_or_create_state("eleanor", "medication")
    assert state.count == 1

    # Exact duplicate event_id 5 seconds later
    t2 = datetime(2026, 10, 10, 8, 30, 5, tzinfo=timezone.utc)
    engine.record_event("eleanor", "medication", t2, event_id="ev_001")
    assert state.count == 1, "Duplicate event_id must not increment count"

    # Rapid successive log within 60s without event_id
    t3 = datetime(2026, 10, 10, 8, 30, 20, tzinfo=timezone.utc)
    engine.record_event("eleanor", "medication", t3)
    assert state.count == 1, "Event within 60s debounce window must not increment count"

    # Advance clock to next day
    t4 = datetime(2026, 10, 11, 8, 32, 0, tzinfo=timezone.utc)
    engine.record_event("eleanor", "medication", t4, event_id="ev_002")
    assert state.count == 2
    assert state.last_event_time == t4

    # Out-of-order event arriving with older timestamp (e.g. sensor backfill from t1 + 2 hours)
    t_old = datetime(2026, 10, 10, 10, 0, 0, tzinfo=timezone.utc)
    z_out, is_anomaly_out = engine.record_event("eleanor", "medication", t_old)
    # Count should NOT increment and last_event_time should NOT regress
    assert state.count == 2
    assert state.last_event_time == t4


def test_daylight_saving_transition():
    """
    Verify:
    When configured with a local timezone (e.g. America/New_York),
    an event occurring at 08:30 AM local time before and after DST switch
    is recognized at 510.0 minutes without generating false anomalies.
    """
    engine = BaselineEngine(min_observations=5)
    engine.set_person_timezone("eleanor", "America/New_York")

    # US DST Fall Back weekend (Oct 31 - Nov 1, 2026):
    # - Saturday Oct 31, 2026 (EDT, UTC-4): 08:30 EDT = 12:30 UTC
    # - Sunday Nov 1, 2026 (EST, UTC-5):    08:30 EST = 13:30 UTC
    edt_time = datetime(2026, 10, 31, 12, 30, 0, tzinfo=timezone.utc)
    est_time = datetime(2026, 11, 1, 13, 30, 0, tzinfo=timezone.utc)

    # 1. Record EDT day
    z1, is_anomaly1 = engine.record_event("eleanor", "medication", edt_time)
    state = engine.get_or_create_state("eleanor", "medication")
    assert state.count == 1
    # 08:30 is 510 minutes
    assert abs(state.mu_minutes - 510.0) < 0.1

    # 2. Record EST day (60 minutes later in UTC, but EXACT same 08:30 in local time!)
    z2, is_anomaly2 = engine.record_event("eleanor", "medication", est_time)
    assert not is_anomaly2
    # Difference in local time must be 0
    assert abs(state.mu_minutes - 510.0) < 0.1


def test_outlier_winsorization_protects_baseline():
    """
    Verify:
    An extreme outlier (|z| > 3.0) is flagged as an anomaly, but its difference
    in EWMA update is clamped to 3*sigma so a single emergency doesn't ruin the baseline.
    """
    engine = BaselineEngine(min_observations=5)

    # Train 6 normal days at 08:30 (510m, sigma ~ 15m)
    for day in range(6):
        t = datetime(2026, 10, 10 + day, 8, 30, 0, tzinfo=timezone.utc)
        engine.record_event("eleanor", "medication", t)

    state = engine.get_or_create_state("eleanor", "medication")
    initial_mu = state.mu_minutes
    initial_sigma = state.sigma
    assert abs(initial_mu - 510.0) < 5.0

    # Extreme outlier: pill logged at 15:30 (7 hours / 420 minutes late!)
    t_outlier = datetime(2026, 10, 16, 15, 30, 0, tzinfo=timezone.utc)
    z, is_anomaly = engine.record_event("eleanor", "medication", t_outlier)

    assert is_anomaly is True
    assert z > 3.0

    # Without winsorization, mu would jump by alpha * 420 = 84 minutes!
    # With winsorization, max jump is alpha * 3 * sigma <= 0.2 * 45 = 9 minutes!
    jump = abs(circular_minute_difference(state.mu_minutes, initial_mu))
    assert jump <= 15.0, f"Winsorized jump was unexpectedly large: {jump:.1f} minutes"


def test_naive_timestamp_rejected():
    """
    Verify:
    Naive datetime without tzinfo raises ValueError to prevent silent mixing of local and UTC.
    """
    engine = BaselineEngine()
    naive_dt = datetime(2026, 10, 20, 8, 30, 0)  # No tzinfo!

    with pytest.raises(ValueError) as excinfo:
        engine.record_event("eleanor", "medication", naive_dt)
    assert "timezone-aware" in str(excinfo.value)

    with pytest.raises(ValueError) as excinfo2:
        engine.evaluate_routine("eleanor", "medication", naive_dt)
    assert "timezone-aware" in str(excinfo2.value)


def test_configurable_min_grace_minutes():
    """
    Verify:
    min_grace_minutes is configurable (e.g. 45 minutes instead of 30).
    """
    engine = BaselineEngine(min_observations=5, min_grace_minutes=45.0)

    for day in range(6):
        t = datetime(2026, 10, 10 + day, 8, 30, 0, tzinfo=timezone.utc)
        engine.record_event("eleanor", "medication", t)

    # Check at 09:05 (35 minutes after expected 08:30).
    # With 30m grace it would be missed. With 45m grace it is STILL PENDING!
    check_time = datetime(2026, 10, 16, 9, 5, 0, tzinfo=timezone.utc)
    eval_res = engine.evaluate_routine("eleanor", "medication", check_time, events_today=[])
    assert eval_res.is_missed is False
    assert eval_res.status == "pending"
    assert eval_res.grace_window_minutes >= 45.0

"""
Unit tests for CareLoop clock abstractions.
"""

from datetime import datetime, timezone, timedelta
import pytest
from careloop.clock import SystemClock, SimulatedClock


def test_system_clock_returns_utc_datetime():
    clock = SystemClock()
    now = clock.now()
    assert isinstance(now, datetime)
    assert now.tzinfo is not None
    assert now.tzinfo == timezone.utc


def test_simulated_clock_default_initialization():
    clock = SimulatedClock()
    now = clock.now()
    assert now == datetime(2026, 10, 20, 7, 0, 0, tzinfo=timezone.utc)


def test_simulated_clock_custom_initialization():
    custom = datetime(2026, 10, 21, 14, 30, 0)
    clock = SimulatedClock(custom)
    now = clock.now()
    assert now == datetime(2026, 10, 21, 14, 30, 0, tzinfo=timezone.utc)


def test_simulated_clock_advance_seconds():
    clock = SimulatedClock(datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc))
    new_time = clock.advance(3600)  # +1 hour
    assert new_time == datetime(2026, 10, 20, 9, 0, 0, tzinfo=timezone.utc)
    assert clock.now() == datetime(2026, 10, 20, 9, 0, 0, tzinfo=timezone.utc)


def test_simulated_clock_advance_timedelta():
    clock = SimulatedClock(datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc))
    new_time = clock.advance(timedelta(days=2, hours=3))
    assert new_time == datetime(2026, 10, 22, 11, 0, 0, tzinfo=timezone.utc)
    assert clock.now() == datetime(2026, 10, 22, 11, 0, 0, tzinfo=timezone.utc)


def test_simulated_clock_set_time():
    clock = SimulatedClock()
    target = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    clock.set_time(target)
    assert clock.now() == target


def test_simulated_clock_invalid_advance_type():
    clock = SimulatedClock()
    with pytest.raises(TypeError):
        clock.advance("invalid")  # type: ignore

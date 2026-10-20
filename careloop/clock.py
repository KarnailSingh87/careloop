"""
Injectable clock abstraction for CareLoop.

Allows all time-dependent logic (anomaly detection, scheduled routines,
voice check-in windows, and alert escalation) to run against real system
time or simulated demo/test time.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
import threading
from typing import Union


class Clock(ABC):
    """Abstract interface for time providers."""

    @abstractmethod
    def now(self) -> datetime:
        """Return the current time, always UTC and timezone-aware."""
        raise NotImplementedError


class SystemClock(Clock):
    """Real-world clock using system UTC time."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class SimulatedClock(Clock):
    """
    Controllable clock for unit tests and interactive hackathon demos.
    
    Can be advanced by seconds, minutes, hours, or jumped to any point in time.
    """

    def __init__(self, initial_time: datetime | None = None) -> None:
        if initial_time is None:
            # Default to a deterministic starting time: 2026-10-20 07:00:00 UTC (Tuesday morning)
            self._current_time = datetime(2026, 10, 20, 7, 0, 0, tzinfo=timezone.utc)
        else:
            if initial_time.tzinfo is None:
                self._current_time = initial_time.replace(tzinfo=timezone.utc)
            else:
                self._current_time = initial_time.astimezone(timezone.utc)
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            return self._current_time

    def advance(self, duration: Union[timedelta, float, int]) -> datetime:
        """
        Advance simulated clock by timedelta or number of seconds.
        Returns the new current time.
        """
        with self._lock:
            if isinstance(duration, (int, float)):
                delta = timedelta(seconds=duration)
            elif isinstance(duration, timedelta):
                delta = duration
            else:
                raise TypeError(f"Expected timedelta, float, or int, got {type(duration)}")
            self._current_time += delta
            return self._current_time

    def set_time(self, target_time: datetime) -> datetime:
        """
        Jump to an exact timestamp.
        Returns the new current time.
        """
        with self._lock:
            if target_time.tzinfo is None:
                self._current_time = target_time.replace(tzinfo=timezone.utc)
            else:
                self._current_time = target_time.astimezone(timezone.utc)
            return self._current_time

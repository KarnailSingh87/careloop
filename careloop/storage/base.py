"""
Abstract storage interface for CareLoop.

Decouples data access from underlying persistence (SQLite locally, DynamoDB on AWS).
Enforces privacy guarantees: only metadata and structured routine logs are persisted.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional
from careloop.models import Event, PersonProfile, Alert, EscalationState, Reminder


class StorageBase(ABC):
    """Abstract Base Class defining the CareLoop storage contract."""

    @abstractmethod
    def save_event(self, event: Event) -> None:
        """Persist a routine event metadata entry."""
        raise NotImplementedError

    @abstractmethod
    def get_events(
        self,
        person_id: str,
        limit: int = 100,
        event_type: Optional[str] = None
    ) -> List[Event]:
        """Fetch recent events for a person, sorted latest first."""
        raise NotImplementedError

    @abstractmethod
    def save_reminder(self, reminder: Reminder) -> None:
        """Persist a scheduled reminder."""
        raise NotImplementedError

    @abstractmethod
    def get_reminders(
        self,
        person_id: str,
        active_only: bool = True
    ) -> List[Reminder]:
        """Fetch reminders for a person."""
        raise NotImplementedError

    @abstractmethod
    def save_profile(self, profile: PersonProfile) -> None:
        """Persist or update an elder's profile."""
        raise NotImplementedError

    @abstractmethod
    def get_profile(self, person_id: str) -> Optional[PersonProfile]:
        """Fetch an elder's profile by person_id."""
        raise NotImplementedError

    @abstractmethod
    def save_alert(self, alert: Alert) -> None:
        """Persist a deterministic alert."""
        raise NotImplementedError

    @abstractmethod
    def get_alerts(
        self,
        person_id: str,
        active_only: bool = True
    ) -> List[Alert]:
        """Fetch alerts for a person."""
        raise NotImplementedError

    @abstractmethod
    def save_escalation_state(self, state: EscalationState) -> None:
        """Persist per-person escalation state machine status."""
        raise NotImplementedError

    @abstractmethod
    def get_escalation_state(self, person_id: str) -> Optional[EscalationState]:
        """Fetch per-person escalation state machine status."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Close any open storage connections or resources."""
        raise NotImplementedError

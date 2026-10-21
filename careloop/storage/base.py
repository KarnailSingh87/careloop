"""
Abstract storage interface for CareLoop.

Decouples data access from underlying persistence (SQLite locally, DynamoDB on AWS).
Enforces privacy guarantees: only approved metadata and structured routine logs are persisted.
Audio, ambient recordings, and sensitive credentials are strictly prohibited.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional
from careloop.models import (
    Event,
    PersonProfile,
    Alert,
    EscalationState,
    Reminder,
    LearnedBaseline,
)


class StorageError(Exception):
    """Base exception for all CareLoop storage failures."""
    pass


class StaleStateError(StorageError):
    """Raised when an escalation state write is rejected due to an optimistic concurrency conflict."""
    pass


class StorageClosedError(StorageError):
    """Raised when attempting an operation on a closed storage instance."""
    pass


class PrivacyViolationError(StorageError):
    """Raised when forbidden audio data or sensitive credentials are submitted to storage."""
    pass


class StorageBase(ABC):
    """Abstract Base Class defining the CareLoop typed storage contract."""

    # --- Events ---
    @abstractmethod
    def save_event(self, event: Event) -> None:
        """
        Persist a routine event metadata entry.
        Idempotent: duplicate submissions with the same event_id are not duplicated.
        Enforces privacy: audio payloads are strictly rejected.
        """
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

    # --- Learned Baselines ---
    @abstractmethod
    def save_baseline(self, baseline: LearnedBaseline) -> None:
        """Persist a learned routine baseline schedule."""
        raise NotImplementedError

    @abstractmethod
    def get_baseline(self, person_id: str, routine_type: str) -> Optional[LearnedBaseline]:
        """Fetch a learned routine baseline by person and routine type."""
        raise NotImplementedError

    @abstractmethod
    def list_baselines(self, person_id: str) -> List[LearnedBaseline]:
        """List all learned routine baselines for a person."""
        raise NotImplementedError

    # --- Reminders ---
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

    # --- Person Profiles ---
    @abstractmethod
    def save_profile(self, profile: PersonProfile) -> None:
        """Persist or update an elder's profile."""
        raise NotImplementedError

    @abstractmethod
    def get_profile(self, person_id: str) -> Optional[PersonProfile]:
        """Fetch an elder's profile by person_id."""
        raise NotImplementedError

    @abstractmethod
    def list_profiles(self) -> List[PersonProfile]:
        """List all elder profiles."""
        raise NotImplementedError

    # --- Alerts & Notification Delivery Status ---
    @abstractmethod
    def save_alert(self, alert: Alert) -> None:
        """Persist a deterministic alert with delivery status tracking."""
        raise NotImplementedError

    @abstractmethod
    def get_alerts(
        self,
        person_id: str,
        active_only: bool = True
    ) -> List[Alert]:
        """Fetch alerts for a person."""
        raise NotImplementedError

    # --- Escalation State Machine ---
    @abstractmethod
    def save_escalation_state(
        self,
        state: EscalationState,
        check_version: bool = False,
    ) -> None:
        """Persist per-person escalation state machine status with optimistic concurrency check."""
        raise NotImplementedError

    @abstractmethod
    def get_escalation_state(self, person_id: str) -> Optional[EscalationState]:
        """Fetch per-person escalation state machine status."""
        raise NotImplementedError

    # --- Demo Isolation ---
    def clear_demo_data(self, person_id: str = "dad") -> None:
        """
        Clear demo-generated events and alerts for an isolated simulation session.
        Strictly preserves baseline profiles and production records.
        """
        pass

    # --- Lifecycle & Context Management ---
    @abstractmethod
    def close(self) -> None:
        """Close any open storage connections or resources."""
        raise NotImplementedError

    def __enter__(self) -> StorageBase:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

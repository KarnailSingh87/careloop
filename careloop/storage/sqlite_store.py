"""
SQLite implementation of the CareLoop storage interface.

Provides zero-dependency local persistence for development, offline testing,
and edge deployments.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import List, Optional

from careloop.models import (
    Event,
    EventType,
    PersonProfile,
    EmergencyContact,
    Alert,
    AlertLevel,
    RoutineType,
    EscalationStage,
    EscalationState,
    Reminder,
    ReminderStatus,
)
from careloop.storage.base import StorageBase


class SQLiteStorage(StorageBase):
    """Local SQLite-backed storage implementation."""

    def __init__(self, db_path: str = "careloop_local.db") -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        """Create necessary tables and indexes if they do not exist."""
        with self._lock:
            with self._conn:
                self._conn.executescript("""
                    CREATE TABLE IF NOT EXISTS events (
                        event_id TEXT PRIMARY KEY,
                        person_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        metadata TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_events_person_time 
                        ON events (person_id, timestamp DESC);
                    CREATE INDEX IF NOT EXISTS idx_events_type 
                        ON events (person_id, event_type);

                    CREATE TABLE IF NOT EXISTS reminders (
                        reminder_id TEXT PRIMARY KEY,
                        person_id TEXT NOT NULL,
                        text TEXT NOT NULL,
                        scheduled_time TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_reminders_person 
                        ON reminders (person_id, status);

                    CREATE TABLE IF NOT EXISTS profiles (
                        person_id TEXT PRIMARY KEY,
                        display_name TEXT NOT NULL,
                        timezone TEXT NOT NULL,
                        emergency_contacts TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS alerts (
                        alert_id TEXT PRIMARY KEY,
                        person_id TEXT NOT NULL,
                        level TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        title TEXT NOT NULL,
                        reasons TEXT NOT NULL,
                        recommended_action TEXT NOT NULL,
                        routine_type TEXT,
                        status TEXT NOT NULL,
                        metadata TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_alerts_person 
                        ON alerts (person_id, status);

                    CREATE TABLE IF NOT EXISTS escalation_states (
                        person_id TEXT PRIMARY KEY,
                        stage TEXT NOT NULL,
                        entered_at TEXT NOT NULL,
                        last_updated TEXT NOT NULL,
                        risk_score REAL NOT NULL,
                        reasons TEXT NOT NULL,
                        metadata TEXT NOT NULL
                    );
                """)

    def save_event(self, event: Event) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO events (event_id, person_id, event_type, timestamp, metadata)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.person_id,
                        event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
                        event.timestamp.isoformat(),
                        json.dumps(event.metadata),
                    ),
                )

    def get_events(
        self,
        person_id: str,
        limit: int = 100,
        event_type: Optional[str] = None
    ) -> List[Event]:
        with self._lock:
            query = "SELECT * FROM events WHERE person_id = ?"
            params: list = [person_id]
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor = self._conn.execute(query, params)
            rows = cursor.fetchall()

        events: List[Event] = []
        for r in rows:
            ts = datetime.fromisoformat(r["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            
            raw_type = r["event_type"]
            # Map known routine strings like "medication" to EventType
            try:
                e_type = EventType(raw_type)
            except ValueError:
                if raw_type == "medication":
                    e_type = EventType.PILL
                else:
                    e_type = EventType.CUSTOM

            events.append(
                Event(
                    event_id=r["event_id"],
                    person_id=r["person_id"],
                    event_type=e_type,
                    timestamp=ts,
                    metadata=json.loads(r["metadata"]),
                )
            )
        return events

    def save_reminder(self, reminder: Reminder) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO reminders (
                        reminder_id, person_id, text, scheduled_time, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        reminder.reminder_id,
                        reminder.person_id,
                        reminder.text,
                        reminder.scheduled_time,
                        reminder.status.value if hasattr(reminder.status, "value") else str(reminder.status),
                        reminder.created_at.isoformat(),
                    ),
                )

    def get_reminders(
        self,
        person_id: str,
        active_only: bool = True
    ) -> List[Reminder]:
        with self._lock:
            if active_only:
                cursor = self._conn.execute(
                    "SELECT * FROM reminders WHERE person_id = ? AND status = ? ORDER BY scheduled_time ASC",
                    (person_id, ReminderStatus.PENDING.value),
                )
            else:
                cursor = self._conn.execute(
                    "SELECT * FROM reminders WHERE person_id = ? ORDER BY scheduled_time ASC",
                    (person_id,),
                )
            rows = cursor.fetchall()

        reminders: List[Reminder] = []
        for r in rows:
            created = datetime.fromisoformat(r["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            reminders.append(
                Reminder(
                    reminder_id=r["reminder_id"],
                    person_id=r["person_id"],
                    text=r["text"],
                    scheduled_time=r["scheduled_time"],
                    status=ReminderStatus(r["status"]),
                    created_at=created,
                )
            )
        return reminders

    def save_profile(self, profile: PersonProfile) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO profiles (
                        person_id, display_name, timezone, emergency_contacts, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        profile.person_id,
                        profile.display_name,
                        profile.timezone,
                        json.dumps([c.model_dump() for c in profile.emergency_contacts]),
                        profile.created_at.isoformat(),
                    ),
                )

    def get_profile(self, person_id: str) -> Optional[PersonProfile]:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM profiles WHERE person_id = ?",
                (person_id,),
            )
            r = cursor.fetchone()

        if not r:
            return None

        contacts_data = json.loads(r["emergency_contacts"])
        contacts = [EmergencyContact(**c) for c in contacts_data]
        created = datetime.fromisoformat(r["created_at"])
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        return PersonProfile(
            person_id=r["person_id"],
            display_name=r["display_name"],
            timezone=r["timezone"],
            emergency_contacts=contacts,
            created_at=created,
        )

    def save_alert(self, alert: Alert) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO alerts (
                        alert_id, person_id, level, created_at, title, reasons,
                        recommended_action, routine_type, status, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        alert.alert_id,
                        alert.person_id,
                        alert.level.value if hasattr(alert.level, "value") else str(alert.level),
                        alert.created_at.isoformat(),
                        alert.title,
                        json.dumps(alert.reasons),
                        alert.recommended_action,
                        alert.routine_type.value if alert.routine_type else None,
                        alert.status,
                        json.dumps(alert.metadata),
                    ),
                )

    def get_alerts(
        self,
        person_id: str,
        active_only: bool = True
    ) -> List[Alert]:
        with self._lock:
            if active_only:
                cursor = self._conn.execute(
                    "SELECT * FROM alerts WHERE person_id = ? AND status = 'ACTIVE' ORDER BY created_at DESC",
                    (person_id,),
                )
            else:
                cursor = self._conn.execute(
                    "SELECT * FROM alerts WHERE person_id = ? ORDER BY created_at DESC",
                    (person_id,),
                )
            rows = cursor.fetchall()

        alerts: List[Alert] = []
        for r in rows:
            created = datetime.fromisoformat(r["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            alerts.append(
                Alert(
                    alert_id=r["alert_id"],
                    person_id=r["person_id"],
                    level=AlertLevel(r["level"]),
                    created_at=created,
                    title=r["title"],
                    reasons=json.loads(r["reasons"]),
                    recommended_action=r["recommended_action"],
                    routine_type=RoutineType(r["routine_type"]) if r["routine_type"] else None,
                    status=r["status"],
                    metadata=json.loads(r["metadata"]),
                )
            )
        return alerts

    def save_escalation_state(self, state: EscalationState) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO escalation_states (
                        person_id, stage, entered_at, last_updated, risk_score, reasons, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        state.person_id,
                        state.stage.value if hasattr(state.stage, "value") else str(state.stage),
                        state.entered_at.isoformat(),
                        state.last_updated.isoformat(),
                        state.risk_score,
                        json.dumps(state.reasons),
                        json.dumps(state.metadata),
                    ),
                )

    def get_escalation_state(self, person_id: str) -> Optional[EscalationState]:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM escalation_states WHERE person_id = ?",
                (person_id,),
            )
            r = cursor.fetchone()

        if not r:
            return None

        entered = datetime.fromisoformat(r["entered_at"])
        if entered.tzinfo is None:
            entered = entered.replace(tzinfo=timezone.utc)

        updated = datetime.fromisoformat(r["last_updated"])
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)

        return EscalationState(
            person_id=r["person_id"],
            stage=EscalationStage(r["stage"]),
            entered_at=entered,
            last_updated=updated,
            risk_score=float(r["risk_score"]),
            reasons=json.loads(r["reasons"]),
            metadata=json.loads(r["metadata"]),
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

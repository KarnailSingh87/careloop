"""
SQLite implementation of the CareLoop storage interface.

Provides zero-dependency, local, transactional persistence for development, offline testing,
and edge deployments with ACID guarantees and safe concurrent access.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
    LearnedBaseline,
)
from careloop.storage.base import (
    StorageBase,
    StorageError,
    StaleStateError,
    StorageClosedError,
    PrivacyViolationError,
)

logger = logging.getLogger(__name__)

FORBIDDEN_AUDIO_KEYS = {
    "audio", "raw_audio", "recording", "voice_recording",
    "audio_bytes", "wav", "mp3", "pcm", "ambient_audio",
}


class SQLiteStorage(StorageBase):
    """Local SQLite-backed storage implementation with WAL mode and thread safety."""

    SCHEMA_VERSION = 3

    def __init__(self, db_path: str = "careloop_local.db") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._closed = False
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # Configure connection for high-concurrency safety
        try:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA busy_timeout=5000;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
        except sqlite3.Error as e:
            logger.debug(f"SQLite PRAGMA initialization notice: {e}")

        self._init_db()

    def _check_closed(self) -> None:
        if self._closed:
            raise StorageClosedError("Storage connection has been closed.")

    def _init_db(self) -> None:
        """Create tables, indexes, and apply versioned migrations."""
        with self._lock:
            self._check_closed()
            with self._conn:
                # 1. Base Tables Creation
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
                        ON events (person_id, event_type, timestamp DESC);

                    CREATE TABLE IF NOT EXISTS reminders (
                        reminder_id TEXT PRIMARY KEY,
                        person_id TEXT NOT NULL,
                        text TEXT NOT NULL,
                        scheduled_time TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_reminders_person 
                        ON reminders (person_id, status, scheduled_time ASC);

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
                        notification_status TEXT NOT NULL DEFAULT 'pending',
                        delivered_at TEXT,
                        delivery_error TEXT,
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        event_ids TEXT NOT NULL DEFAULT '[]',
                        metadata TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_alerts_person 
                        ON alerts (person_id, status, created_at DESC);

                    CREATE TABLE IF NOT EXISTS escalation_states (
                        person_id TEXT PRIMARY KEY,
                        stage TEXT NOT NULL,
                        entered_at TEXT NOT NULL,
                        last_updated TEXT NOT NULL,
                        risk_score REAL NOT NULL,
                        reasons TEXT NOT NULL,
                        event_references TEXT NOT NULL DEFAULT '[]',
                        notification_state TEXT NOT NULL DEFAULT 'none',
                        notification_id TEXT,
                        version INTEGER NOT NULL DEFAULT 1,
                        metadata TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS baselines (
                        person_id TEXT NOT NULL,
                        routine_type TEXT NOT NULL,
                        sample_count INTEGER NOT NULL,
                        mean_time_minutes REAL NOT NULL,
                        std_dev_minutes REAL NOT NULL,
                        earliest_time TEXT NOT NULL,
                        latest_time TEXT NOT NULL,
                        confidence_score REAL NOT NULL,
                        last_updated TEXT NOT NULL,
                        PRIMARY KEY (person_id, routine_type)
                    );
                    CREATE INDEX IF NOT EXISTS idx_baselines_person 
                        ON baselines (person_id);
                """)

                # 2. Incremental Migrations via PRAGMA user_version
                cursor = self._conn.execute("PRAGMA user_version")
                current_ver = cursor.fetchone()[0]

                # Migration for legacy escalation_states columns
                cursor = self._conn.execute("PRAGMA table_info(escalation_states)")
                esc_cols = [r["name"] for r in cursor.fetchall()]
                if "version" not in esc_cols:
                    self._conn.execute("ALTER TABLE escalation_states ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
                if "event_references" not in esc_cols:
                    self._conn.execute("ALTER TABLE escalation_states ADD COLUMN event_references TEXT NOT NULL DEFAULT '[]'")
                if "notification_state" not in esc_cols:
                    self._conn.execute("ALTER TABLE escalation_states ADD COLUMN notification_state TEXT NOT NULL DEFAULT 'none'")
                if "notification_id" not in esc_cols:
                    self._conn.execute("ALTER TABLE escalation_states ADD COLUMN notification_id TEXT")

                # Migration for legacy alerts columns
                cursor = self._conn.execute("PRAGMA table_info(alerts)")
                alert_cols = [r["name"] for r in cursor.fetchall()]
                if "notification_status" not in alert_cols:
                    self._conn.execute("ALTER TABLE alerts ADD COLUMN notification_status TEXT NOT NULL DEFAULT 'pending'")
                if "delivered_at" not in alert_cols:
                    self._conn.execute("ALTER TABLE alerts ADD COLUMN delivered_at TEXT")
                if "delivery_error" not in alert_cols:
                    self._conn.execute("ALTER TABLE alerts ADD COLUMN delivery_error TEXT")
                if "retry_count" not in alert_cols:
                    self._conn.execute("ALTER TABLE alerts ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0")
                if "event_ids" not in alert_cols:
                    self._conn.execute("ALTER TABLE alerts ADD COLUMN event_ids TEXT NOT NULL DEFAULT '[]'")

                if current_ver < self.SCHEMA_VERSION:
                    self._conn.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION};")

    def save_event(self, event: Event) -> None:
        """
        Persist a routine event metadata entry.
        Enforces privacy: audio payloads are strictly rejected.
        Idempotent: events with duplicate event_id are not duplicated.
        """
        with self._lock:
            self._check_closed()

            # 1. Validation & Privacy Enforcement
            if not event.event_id:
                event.event_id = str(uuid.uuid4())

            if event.timestamp.tzinfo is None:
                raise ValueError(f"Event timestamp {event.timestamp} must be timezone-aware.")

            if event.metadata:
                forbidden = FORBIDDEN_AUDIO_KEYS.intersection(k.lower() for k in event.metadata.keys())
                if forbidden:
                    raise PrivacyViolationError(
                        f"Privacy violation: Audio/recording fields {forbidden} are strictly forbidden from CareLoop storage."
                    )

            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO events (event_id, person_id, event_type, timestamp, metadata)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(event_id) DO NOTHING
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
            self._check_closed()
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

    # --- Baselines ---
    def save_baseline(self, baseline: LearnedBaseline) -> None:
        with self._lock:
            self._check_closed()
            routine_type_str = (
                baseline.routine_type.value
                if hasattr(baseline.routine_type, "value")
                else str(baseline.routine_type)
            )
            with self._conn:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO baselines (
                        person_id, routine_type, sample_count, mean_time_minutes,
                        std_dev_minutes, earliest_time, latest_time, confidence_score, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        baseline.person_id,
                        routine_type_str,
                        baseline.sample_count,
                        baseline.mean_time_minutes,
                        baseline.std_dev_minutes,
                        baseline.earliest_time,
                        baseline.latest_time,
                        baseline.confidence_score,
                        baseline.last_updated.isoformat(),
                    ),
                )

    def get_baseline(self, person_id: str, routine_type: str) -> Optional[LearnedBaseline]:
        with self._lock:
            self._check_closed()
            cursor = self._conn.execute(
                "SELECT * FROM baselines WHERE person_id = ? AND routine_type = ?",
                (person_id, routine_type),
            )
            r = cursor.fetchone()

        if not r:
            return None

        last_updated = datetime.fromisoformat(r["last_updated"])
        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=timezone.utc)

        raw_routine = r["routine_type"]
        try:
            r_type = RoutineType(raw_routine)
        except ValueError:
            r_type = raw_routine

        return LearnedBaseline(
            person_id=r["person_id"],
            routine_type=r_type,
            sample_count=int(r["sample_count"]),
            mean_time_minutes=float(r["mean_time_minutes"]),
            std_dev_minutes=float(r["std_dev_minutes"]),
            earliest_time=r["earliest_time"],
            latest_time=r["latest_time"],
            confidence_score=float(r["confidence_score"]),
            last_updated=last_updated,
        )

    def list_baselines(self, person_id: str) -> List[LearnedBaseline]:
        with self._lock:
            self._check_closed()
            cursor = self._conn.execute(
                "SELECT * FROM baselines WHERE person_id = ? ORDER BY routine_type ASC",
                (person_id,),
            )
            rows = cursor.fetchall()

        baselines: List[LearnedBaseline] = []
        for r in rows:
            last_updated = datetime.fromisoformat(r["last_updated"])
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)

            raw_routine = r["routine_type"]
            try:
                r_type = RoutineType(raw_routine)
            except ValueError:
                r_type = raw_routine

            baselines.append(
                LearnedBaseline(
                    person_id=r["person_id"],
                    routine_type=r_type,
                    sample_count=int(r["sample_count"]),
                    mean_time_minutes=float(r["mean_time_minutes"]),
                    std_dev_minutes=float(r["std_dev_minutes"]),
                    earliest_time=r["earliest_time"],
                    latest_time=r["latest_time"],
                    confidence_score=float(r["confidence_score"]),
                    last_updated=last_updated,
                )
            )
        return baselines

    # --- Reminders ---
    def save_reminder(self, reminder: Reminder) -> None:
        with self._lock:
            self._check_closed()
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
            self._check_closed()
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

    # --- Profiles ---
    def save_profile(self, profile: PersonProfile) -> None:
        with self._lock:
            self._check_closed()
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
            self._check_closed()
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

    def list_profiles(self) -> List[PersonProfile]:
        with self._lock:
            self._check_closed()
            cursor = self._conn.execute("SELECT * FROM profiles ORDER BY person_id ASC")
            rows = cursor.fetchall()

        profiles: List[PersonProfile] = []
        for r in rows:
            contacts_data = json.loads(r["emergency_contacts"])
            contacts = [EmergencyContact(**c) for c in contacts_data]
            created = datetime.fromisoformat(r["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            profiles.append(
                PersonProfile(
                    person_id=r["person_id"],
                    display_name=r["display_name"],
                    timezone=r["timezone"],
                    emergency_contacts=contacts,
                    created_at=created,
                )
            )
        return profiles

    # --- Alerts ---
    def save_alert(self, alert: Alert) -> None:
        with self._lock:
            self._check_closed()
            with self._conn:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO alerts (
                        alert_id, person_id, level, created_at, title, reasons,
                        recommended_action, routine_type, status, notification_status,
                        delivered_at, delivery_error, retry_count, event_ids, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        alert.notification_status,
                        alert.delivered_at.isoformat() if alert.delivered_at else None,
                        alert.delivery_error,
                        alert.retry_count,
                        json.dumps(alert.event_ids),
                        json.dumps(alert.metadata),
                    ),
                )

    def get_alerts(
        self,
        person_id: str,
        active_only: bool = True
    ) -> List[Alert]:
        with self._lock:
            self._check_closed()
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

            delivered = None
            if "delivered_at" in r.keys() and r["delivered_at"]:
                delivered = datetime.fromisoformat(r["delivered_at"])
                if delivered.tzinfo is None:
                    delivered = delivered.replace(tzinfo=timezone.utc)

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
                    notification_status=r["notification_status"] if "notification_status" in r.keys() else "pending",
                    delivered_at=delivered,
                    delivery_error=r["delivery_error"] if "delivery_error" in r.keys() else None,
                    retry_count=int(r["retry_count"]) if "retry_count" in r.keys() else 0,
                    event_ids=json.loads(r["event_ids"]) if ("event_ids" in r.keys() and r["event_ids"]) else [],
                    metadata=json.loads(r["metadata"]),
                )
            )
        return alerts

    # --- Escalation State ---
    def save_escalation_state(
        self,
        state: EscalationState,
        check_version: bool = False,
    ) -> None:
        with self._lock:
            self._check_closed()
            with self._conn:
                if check_version:
                    cursor = self._conn.execute(
                        "SELECT version, last_updated FROM escalation_states WHERE person_id = ?",
                        (state.person_id,),
                    )
                    row = cursor.fetchone()
                    if row:
                        curr_ver = int(row["version"]) if "version" in row.keys() else 1
                        curr_ts = datetime.fromisoformat(row["last_updated"])
                        if curr_ts.tzinfo is None:
                            curr_ts = curr_ts.replace(tzinfo=timezone.utc)

                        # Reject stale update if stored version is newer
                        if curr_ver > state.version:
                            raise StaleStateError(
                                f"Stale write rejected for {state.person_id}: stored version={curr_ver} > state version={state.version}"
                            )

                        cursor = self._conn.execute(
                            """
                            UPDATE escalation_states
                            SET stage = ?, entered_at = ?, last_updated = ?, risk_score = ?,
                                reasons = ?, event_references = ?, notification_state = ?,
                                notification_id = ?, version = version + 1, metadata = ?
                            WHERE person_id = ? AND version = ?
                            """,
                            (
                                state.stage.value if hasattr(state.stage, "value") else str(state.stage),
                                state.entered_at.isoformat(),
                                state.last_updated.isoformat(),
                                state.risk_score,
                                json.dumps(state.reasons),
                                json.dumps(state.event_references),
                                state.notification_state,
                                state.notification_id,
                                json.dumps(state.metadata),
                                state.person_id,
                                state.version,
                            ),
                        )
                        if cursor.rowcount == 0:
                            raise StaleStateError(
                                f"Optimistic lock conflict: version {state.version} already modified for {state.person_id}"
                            )
                        state.version += 1
                        return

                # Atomic insert or unconditional write
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO escalation_states (
                        person_id, stage, entered_at, last_updated, risk_score, reasons,
                        event_references, notification_state, notification_id, version, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        state.person_id,
                        state.stage.value if hasattr(state.stage, "value") else str(state.stage),
                        state.entered_at.isoformat(),
                        state.last_updated.isoformat(),
                        state.risk_score,
                        json.dumps(state.reasons),
                        json.dumps(state.event_references),
                        state.notification_state,
                        state.notification_id,
                        state.version,
                        json.dumps(state.metadata),
                    ),
                )

    def get_escalation_state(self, person_id: str) -> Optional[EscalationState]:
        with self._lock:
            self._check_closed()
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

        ev_refs = json.loads(r["event_references"]) if ("event_references" in r.keys() and r["event_references"]) else []
        notif_state = r["notification_state"] if "notification_state" in r.keys() else "none"
        notif_id = r["notification_id"] if "notification_id" in r.keys() else None
        version = int(r["version"]) if "version" in r.keys() else 1

        return EscalationState(
            person_id=r["person_id"],
            stage=EscalationStage(r["stage"]),
            entered_at=entered,
            last_updated=updated,
            risk_score=float(r["risk_score"]),
            reasons=json.loads(r["reasons"]),
            event_references=ev_refs,
            notification_state=notif_state,
            notification_id=notif_id,
            version=version,
            metadata=json.loads(r["metadata"]),
        )

    def clear_demo_data(self, person_id: str = "dad") -> None:
        """
        Clear demo-generated events and alerts for an isolated simulation session.
        Preserves baseline profiles, historical benchmark data, and other persons.
        """
        with self._lock:
            self._check_closed()
            with self._conn:
                self._conn.execute(
                    """
                    DELETE FROM events
                    WHERE person_id = ?
                      AND (
                        event_id LIKE 'demo_%'
                        OR json_extract(metadata, '$.source') IN ('simulator_demo', 'simulator_manual')
                      )
                    """,
                    (person_id,),
                )
                self._conn.execute(
                    """
                    DELETE FROM alerts
                    WHERE person_id = ?
                      AND (
                        alert_id LIKE 'demo_%'
                        OR json_extract(metadata, '$.source') = 'simulator_demo'
                        OR title LIKE '%Dad Unresponsive%'
                      )
                    """,
                    (person_id,),
                )

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._conn.close()
                self._closed = True

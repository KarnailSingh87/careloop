"""
AWS DynamoDB implementation of the CareLoop typed storage interface.

Supports single-table design for AWS Builder Challenge and cloud deployments.
Schema:
  - Partition Key (PK): PERSON#{person_id}
  - Sort Key (SK): 
      * EVENT#{timestamp}#{event_id}
      * BASELINE#{routine_type}
      * PROFILE
      * REMINDER#{scheduled_time}#{reminder_id}
      * ALERT#{created_at}#{alert_id}
      * ESCALATION_STATE
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

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


class DynamoDBStorage(StorageBase):
    """DynamoDB storage adapter using AWS boto3 with single-table design and retries."""

    def __init__(
        self,
        table_name: str = "CareLoopData",
        region_name: str = "us-east-1",
        endpoint_url: Optional[str] = None,
        dynamodb_resource: Optional[Any] = None,
    ) -> None:
        self.table_name = table_name
        self.region_name = region_name
        self._closed = False

        if dynamodb_resource is not None:
            self._dynamodb = dynamodb_resource
        else:
            # Configure adaptive client-level retry policy for transient AWS errors
            retry_config = Config(
                retries={"max_attempts": 5, "mode": "adaptive"}
            )
            self._dynamodb = boto3.resource(
                "dynamodb",
                region_name=self.region_name,
                endpoint_url=endpoint_url,
                config=retry_config,
            )

        self._table = self._dynamodb.Table(self.table_name)

    def _check_closed(self) -> None:
        if self._closed:
            raise StorageClosedError("DynamoDB storage adapter is closed.")

    def verify_table(self) -> bool:
        """
        Verify table existence and accessibility.
        Raises StorageError if the configured table cannot be contacted.
        """
        self._check_closed()
        try:
            if hasattr(self._table, "load"):
                self._table.load()
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            raise StorageError(
                f"Failed to access DynamoDB table '{self.table_name}' in region '{self.region_name}' ({error_code}): {e}"
            ) from e

    # --- Events ---
    def save_event(self, event: Event) -> None:
        """
        Persist a routine event metadata entry to DynamoDB.
        Idempotent: Duplicate submissions with the same event_id and timestamp are safely ignored.
        Enforces privacy: Audio payloads are strictly rejected.
        """
        self._check_closed()

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

        item = {
            "PK": f"PERSON#{event.person_id}",
            "SK": f"EVENT#{event.timestamp.isoformat()}#{event.event_id}",
            "event_id": event.event_id,
            "person_id": event.person_id,
            "event_type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
            "timestamp": event.timestamp.isoformat(),
            "metadata": json.dumps(event.metadata),
            "item_type": "EVENT",
        }

        try:
            # Conditional write ensures idempotent deduplication
            self._table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
            )
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                logger.debug(f"Idempotent event duplicate ignored: {event.event_id}")
                return
            logger.error(f"Failed to save event to DynamoDB: {e}")
            raise StorageError(f"DynamoDB save_event failed: {e}") from e

    def get_events(
        self,
        person_id: str,
        limit: int = 100,
        event_type: Optional[str] = None
    ) -> List[Event]:
        self._check_closed()
        try:
            events: List[Event] = []
            query_kwargs: Dict[str, Any] = {
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :sk_prefix)",
                "ExpressionAttributeValues": {
                    ":pk": f"PERSON#{person_id}",
                    ":sk_prefix": "EVENT#",
                },
                "ScanIndexForward": False,  # Latest first
            }

            while True:
                response = self._table.query(**query_kwargs)
                items = response.get("Items", [])
                for item in items:
                    if event_type and item.get("event_type") != event_type:
                        continue
                    ts = datetime.fromisoformat(item["timestamp"])
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    raw_type = item.get("event_type", "")
                    try:
                        e_type = EventType(raw_type)
                    except ValueError:
                        if raw_type == "medication":
                            e_type = EventType.PILL
                        else:
                            e_type = EventType.CUSTOM

                    events.append(
                        Event(
                            event_id=item["event_id"],
                            person_id=item["person_id"],
                            event_type=e_type,
                            timestamp=ts,
                            metadata=json.loads(item["metadata"]),
                        )
                    )
                    if len(events) >= limit:
                        break

                if len(events) >= limit or "LastEvaluatedKey" not in response:
                    break
                query_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

            return events
        except ClientError as e:
            logger.error(f"Failed to query events from DynamoDB: {e}")
            raise StorageError(f"DynamoDB get_events failed: {e}") from e

    # --- Baselines ---
    def save_baseline(self, baseline: LearnedBaseline) -> None:
        self._check_closed()
        routine_type_str = (
            baseline.routine_type.value
            if hasattr(baseline.routine_type, "value")
            else str(baseline.routine_type)
        )
        try:
            item = {
                "PK": f"PERSON#{baseline.person_id}",
                "SK": f"BASELINE#{routine_type_str}",
                "person_id": baseline.person_id,
                "routine_type": routine_type_str,
                "sample_count": baseline.sample_count,
                "mean_time_minutes": str(baseline.mean_time_minutes),
                "std_dev_minutes": str(baseline.std_dev_minutes),
                "earliest_time": baseline.earliest_time,
                "latest_time": baseline.latest_time,
                "confidence_score": str(baseline.confidence_score),
                "last_updated": baseline.last_updated.isoformat(),
                "item_type": "BASELINE",
            }
            self._table.put_item(Item=item)
        except ClientError as e:
            logger.error(f"Failed to save baseline to DynamoDB: {e}")
            raise StorageError(f"DynamoDB save_baseline failed: {e}") from e

    def get_baseline(self, person_id: str, routine_type: str) -> Optional[LearnedBaseline]:
        self._check_closed()
        try:
            response = self._table.get_item(
                Key={
                    "PK": f"PERSON#{person_id}",
                    "SK": f"BASELINE#{routine_type}",
                }
            )
            item = response.get("Item")
            if not item:
                return None

            last_updated = datetime.fromisoformat(item["last_updated"])
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)

            raw_routine = item["routine_type"]
            try:
                r_type = RoutineType(raw_routine)
            except ValueError:
                r_type = raw_routine

            return LearnedBaseline(
                person_id=item["person_id"],
                routine_type=r_type,
                sample_count=int(item["sample_count"]),
                mean_time_minutes=float(item["mean_time_minutes"]),
                std_dev_minutes=float(item["std_dev_minutes"]),
                earliest_time=item["earliest_time"],
                latest_time=item["latest_time"],
                confidence_score=float(item["confidence_score"]),
                last_updated=last_updated,
            )
        except ClientError as e:
            logger.error(f"Failed to get baseline from DynamoDB: {e}")
            raise StorageError(f"DynamoDB get_baseline failed: {e}") from e

    def list_baselines(self, person_id: str) -> List[LearnedBaseline]:
        self._check_closed()
        try:
            baselines: List[LearnedBaseline] = []
            query_kwargs: Dict[str, Any] = {
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :sk_prefix)",
                "ExpressionAttributeValues": {
                    ":pk": f"PERSON#{person_id}",
                    ":sk_prefix": "BASELINE#",
                },
            }

            while True:
                response = self._table.query(**query_kwargs)
                items = response.get("Items", [])
                for item in items:
                    last_updated = datetime.fromisoformat(item["last_updated"])
                    if last_updated.tzinfo is None:
                        last_updated = last_updated.replace(tzinfo=timezone.utc)

                    raw_routine = item["routine_type"]
                    try:
                        r_type = RoutineType(raw_routine)
                    except ValueError:
                        r_type = raw_routine

                    baselines.append(
                        LearnedBaseline(
                            person_id=item["person_id"],
                            routine_type=r_type,
                            sample_count=int(item["sample_count"]),
                            mean_time_minutes=float(item["mean_time_minutes"]),
                            std_dev_minutes=float(item["std_dev_minutes"]),
                            earliest_time=item["earliest_time"],
                            latest_time=item["latest_time"],
                            confidence_score=float(item["confidence_score"]),
                            last_updated=last_updated,
                        )
                    )
                if "LastEvaluatedKey" not in response:
                    break
                query_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

            return baselines
        except ClientError as e:
            logger.error(f"Failed to list baselines from DynamoDB: {e}")
            raise StorageError(f"DynamoDB list_baselines failed: {e}") from e

    # --- Reminders ---
    def save_reminder(self, reminder: Reminder) -> None:
        self._check_closed()
        try:
            item = {
                "PK": f"PERSON#{reminder.person_id}",
                "SK": f"REMINDER#{reminder.scheduled_time}#{reminder.reminder_id}",
                "reminder_id": reminder.reminder_id,
                "person_id": reminder.person_id,
                "text": reminder.text,
                "scheduled_time": reminder.scheduled_time,
                "status": reminder.status.value if hasattr(reminder.status, "value") else str(reminder.status),
                "created_at": reminder.created_at.isoformat(),
                "completed_at": reminder.completed_at.isoformat() if reminder.completed_at else None,
                "error": reminder.error,
                "metadata": json.dumps(reminder.metadata),
                "item_type": "REMINDER",
            }
            self._table.put_item(Item=item)
        except ClientError as e:
            logger.error(f"Failed to save reminder to DynamoDB: {e}")
            raise StorageError(f"DynamoDB save_reminder failed: {e}") from e

    def get_reminders(
        self,
        person_id: str,
        active_only: bool = True
    ) -> List[Reminder]:
        self._check_closed()
        try:
            reminders: List[Reminder] = []
            query_kwargs: Dict[str, Any] = {
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :sk_prefix)",
                "ExpressionAttributeValues": {
                    ":pk": f"PERSON#{person_id}",
                    ":sk_prefix": "REMINDER#",
                },
                "ScanIndexForward": True,  # Ascending order
            }

            while True:
                response = self._table.query(**query_kwargs)
                items = response.get("Items", [])
                for item in items:
                    if active_only and item.get("status") != ReminderStatus.PENDING.value:
                        continue
                    created = datetime.fromisoformat(item["created_at"])
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    completed = None
                    if item.get("completed_at"):
                        completed = datetime.fromisoformat(item["completed_at"])
                        if completed.tzinfo is None:
                            completed = completed.replace(tzinfo=timezone.utc)
                    meta = {}
                    if item.get("metadata"):
                        try:
                            meta = json.loads(item["metadata"])
                        except Exception:
                            meta = {}
                    reminders.append(
                        Reminder(
                            reminder_id=item["reminder_id"],
                            person_id=item["person_id"],
                            text=item["text"],
                            scheduled_time=item["scheduled_time"],
                            status=ReminderStatus(item["status"]),
                            created_at=created,
                            completed_at=completed,
                            error=item.get("error"),
                            metadata=meta,
                        )
                    )
                if "LastEvaluatedKey" not in response:
                    break
                query_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

            return reminders
        except ClientError as e:
            logger.error(f"Failed to query reminders from DynamoDB: {e}")
            raise StorageError(f"DynamoDB get_reminders failed: {e}") from e

    # --- Profiles ---
    def save_profile(self, profile: PersonProfile) -> None:
        self._check_closed()
        try:
            item = {
                "PK": f"PERSON#{profile.person_id}",
                "SK": "PROFILE",
                "person_id": profile.person_id,
                "display_name": profile.display_name,
                "timezone": profile.timezone,
                "emergency_contacts": json.dumps([c.model_dump() for c in profile.emergency_contacts]),
                "created_at": profile.created_at.isoformat(),
                "item_type": "PROFILE",
            }
            self._table.put_item(Item=item)
        except ClientError as e:
            logger.error(f"Failed to save profile to DynamoDB: {e}")
            raise StorageError(f"DynamoDB save_profile failed: {e}") from e

    def get_profile(self, person_id: str) -> Optional[PersonProfile]:
        self._check_closed()
        try:
            response = self._table.get_item(
                Key={
                    "PK": f"PERSON#{person_id}",
                    "SK": "PROFILE",
                }
            )
            item = response.get("Item")
            if not item:
                return None
            contacts = [EmergencyContact(**c) for c in json.loads(item["emergency_contacts"])]
            created = datetime.fromisoformat(item["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            return PersonProfile(
                person_id=item["person_id"],
                display_name=item["display_name"],
                timezone=item["timezone"],
                emergency_contacts=contacts,
                created_at=created,
            )
        except ClientError as e:
            logger.error(f"Failed to get profile from DynamoDB: {e}")
            raise StorageError(f"DynamoDB get_profile failed: {e}") from e

    def list_profiles(self) -> List[PersonProfile]:
        self._check_closed()
        try:
            profiles: List[PersonProfile] = []
            scan_kwargs: Dict[str, Any] = {
                "FilterExpression": "SK = :sk",
                "ExpressionAttributeValues": {":sk": "PROFILE"},
            }

            while True:
                response = self._table.scan(**scan_kwargs)
                items = response.get("Items", [])
                for item in items:
                    contacts = [EmergencyContact(**c) for c in json.loads(item.get("emergency_contacts", "[]"))]
                    created = datetime.fromisoformat(item["created_at"])
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    profiles.append(
                        PersonProfile(
                            person_id=item["person_id"],
                            display_name=item["display_name"],
                            timezone=item.get("timezone", "America/New_York"),
                            emergency_contacts=contacts,
                            created_at=created,
                        )
                    )
                if "LastEvaluatedKey" not in response:
                    break
                scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

            return sorted(profiles, key=lambda p: p.person_id)
        except ClientError as e:
            logger.error(f"Failed to list profiles from DynamoDB: {e}")
            raise StorageError(f"DynamoDB list_profiles failed: {e}") from e

    # --- Alerts ---
    def save_alert(self, alert: Alert) -> None:
        self._check_closed()
        try:
            item = {
                "PK": f"PERSON#{alert.person_id}",
                "SK": f"ALERT#{alert.created_at.isoformat()}#{alert.alert_id}",
                "alert_id": alert.alert_id,
                "person_id": alert.person_id,
                "level": alert.level.value if hasattr(alert.level, "value") else str(alert.level),
                "created_at": alert.created_at.isoformat(),
                "title": alert.title,
                "reasons": json.dumps(alert.reasons),
                "recommended_action": alert.recommended_action,
                "routine_type": alert.routine_type.value if alert.routine_type else None,
                "status": alert.status,
                "notification_status": alert.notification_status,
                "severity": alert.severity,
                "dedup_key": alert.dedup_key,
                "message_id": alert.message_id,
                "accepted_at": alert.accepted_at.isoformat() if alert.accepted_at else None,
                "delivered_at": alert.delivered_at.isoformat() if alert.delivered_at else None,
                "delivery_error": alert.delivery_error,
                "retry_count": alert.retry_count,
                "event_ids": json.dumps(alert.event_ids),
                "metadata": json.dumps(alert.metadata),
                "item_type": "ALERT",
            }
            self._table.put_item(Item=item)
        except ClientError as e:
            logger.error(f"Failed to save alert to DynamoDB: {e}")
            raise StorageError(f"DynamoDB save_alert failed: {e}") from e

    def get_alerts(
        self,
        person_id: str,
        active_only: bool = True
    ) -> List[Alert]:
        self._check_closed()
        try:
            alerts: List[Alert] = []
            query_kwargs: Dict[str, Any] = {
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :sk_prefix)",
                "ExpressionAttributeValues": {
                    ":pk": f"PERSON#{person_id}",
                    ":sk_prefix": "ALERT#",
                },
                "ScanIndexForward": False,
            }

            while True:
                response = self._table.query(**query_kwargs)
                items = response.get("Items", [])
                for item in items:
                    if active_only and item.get("status") != "ACTIVE":
                        continue
                    created = datetime.fromisoformat(item["created_at"])
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    delivered = None
                    if item.get("delivered_at"):
                        delivered = datetime.fromisoformat(item["delivered_at"])
                        if delivered.tzinfo is None:
                            delivered = delivered.replace(tzinfo=timezone.utc)
                    accepted = None
                    if item.get("accepted_at"):
                        accepted = datetime.fromisoformat(item["accepted_at"])
                        if accepted.tzinfo is None:
                            accepted = accepted.replace(tzinfo=timezone.utc)
                    alerts.append(
                        Alert(
                            alert_id=item["alert_id"],
                            person_id=item["person_id"],
                            level=AlertLevel(item["level"]),
                            created_at=created,
                            title=item["title"],
                            reasons=json.loads(item["reasons"]),
                            recommended_action=item["recommended_action"],
                            routine_type=RoutineType(item["routine_type"]) if item.get("routine_type") else None,
                            status=item["status"],
                            notification_status=item.get("notification_status", "pending"),
                            severity=item.get("severity", "high"),
                            dedup_key=item.get("dedup_key", ""),
                            message_id=item.get("message_id"),
                            accepted_at=accepted,
                            delivered_at=delivered,
                            delivery_error=item.get("delivery_error"),
                            retry_count=int(item.get("retry_count", 0)),
                            event_ids=json.loads(item.get("event_ids", "[]")),
                            metadata=json.loads(item["metadata"]),
                        )
                    )
                if "LastEvaluatedKey" not in response:
                    break
                query_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

            return alerts
        except ClientError as e:
            logger.error(f"Failed to query alerts from DynamoDB: {e}")
            raise StorageError(f"DynamoDB get_alerts failed: {e}") from e

    def get_alert_by_dedup_key(
        self,
        person_id: str,
        dedup_key: str,
    ) -> Optional[Alert]:
        alerts = self.get_alerts(person_id, active_only=False)
        for a in alerts:
            if a.dedup_key == dedup_key:
                return a
        return None

    # --- Escalation State ---
    def save_escalation_state(
        self,
        state: EscalationState,
        check_version: bool = False,
    ) -> None:
        self._check_closed()
        try:
            item = {
                "PK": f"PERSON#{state.person_id}",
                "SK": "ESCALATION_STATE",
                "person_id": state.person_id,
                "stage": state.stage.value if hasattr(state.stage, "value") else str(state.stage),
                "entered_at": state.entered_at.isoformat(),
                "last_updated": state.last_updated.isoformat(),
                "risk_score": str(state.risk_score),
                "reasons": json.dumps(state.reasons),
                "event_references": json.dumps(state.event_references),
                "notification_state": state.notification_state,
                "notification_id": state.notification_id,
                "version": state.version,
                "metadata": json.dumps(state.metadata),
                "item_type": "ESCALATION_STATE",
            }
            if check_version:
                try:
                    new_ver = state.version + 1
                    item["version"] = new_ver
                    self._table.put_item(
                        Item=item,
                        ConditionExpression="attribute_not_exists(PK) OR version = :ver",
                        ExpressionAttributeValues={":ver": state.version},
                    )
                    state.version = new_ver
                except ClientError as e:
                    if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                        raise StaleStateError(
                            f"Optimistic lock conflict on DynamoDB for {state.person_id}: version {state.version} already modified"
                        ) from e
                    raise
            else:
                self._table.put_item(Item=item)
        except ClientError as e:
            logger.error(f"Failed to save escalation state to DynamoDB: {e}")
            raise StorageError(f"DynamoDB save_escalation_state failed: {e}") from e

    def get_escalation_state(self, person_id: str) -> Optional[EscalationState]:
        self._check_closed()
        try:
            response = self._table.get_item(
                Key={
                    "PK": f"PERSON#{person_id}",
                    "SK": "ESCALATION_STATE",
                }
            )
            item = response.get("Item")
            if not item:
                return None
            entered = datetime.fromisoformat(item["entered_at"])
            if entered.tzinfo is None:
                entered = entered.replace(tzinfo=timezone.utc)
            updated = datetime.fromisoformat(item["last_updated"])
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            return EscalationState(
                person_id=item["person_id"],
                stage=EscalationStage(item["stage"]),
                entered_at=entered,
                last_updated=updated,
                risk_score=float(item["risk_score"]),
                reasons=json.loads(item["reasons"]),
                event_references=json.loads(item.get("event_references", "[]")),
                notification_state=item.get("notification_state", "none"),
                notification_id=item.get("notification_id"),
                version=int(item.get("version", 1)),
                metadata=json.loads(item["metadata"]),
            )
        except ClientError as e:
            logger.error(f"Failed to get escalation state from DynamoDB: {e}")
            raise StorageError(f"DynamoDB get_escalation_state failed: {e}") from e

    def clear_demo_data(self, person_id: str = "dad") -> None:
        """
        Clear demo-generated events and alerts for an isolated simulation session.
        Preserves baseline profiles, historical benchmark data, and other persons.
        """
        self._check_closed()
        try:
            # Query demo events
            res = self._table.query(
                KeyConditionExpression=Key("PK").eq(f"PERSON#{person_id}") & Key("SK").begins_with("EVENT#")
            )
            for item in res.get("Items", []):
                meta = json.loads(item.get("metadata", "{}"))
                if meta.get("source") in ("simulator_demo", "simulator_manual") or item.get("event_id", "").startswith("demo_"):
                    self._table.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})

            # Query demo alerts
            res_alerts = self._table.query(
                KeyConditionExpression=Key("PK").eq(f"PERSON#{person_id}") & Key("SK").begins_with("ALERT#")
            )
            for item in res_alerts.get("Items", []):
                if item.get("alert_id", "").startswith("demo_") or "Dad Unresponsive" in item.get("title", ""):
                    self._table.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
        except ClientError as e:
            logger.error(f"Failed to clear demo data from DynamoDB: {e}")
            raise StorageError(f"DynamoDB clear_demo_data failed: {e}") from e

    def close(self) -> None:
        self._closed = True

"""
AWS DynamoDB implementation of the CareLoop storage interface.

Supports single-table design for AWS Builder Challenge and cloud deployments.
Schema:
  - Partition Key (PK): PERSON#{person_id}
  - Sort Key (SK): EVENT#{timestamp}#{event_id} | REMINDER#{reminder_id} | ALERT#{created_at}#{alert_id} | PROFILE
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
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
)
from careloop.storage.base import StorageBase

logger = logging.getLogger(__name__)


class DynamoDBStorage(StorageBase):
    """DynamoDB storage adapter using AWS boto3."""

    def __init__(
        self,
        table_name: str = "CareLoopData",
        region_name: str = "us-east-1",
        endpoint_url: Optional[str] = None,
        dynamodb_resource: Optional[Any] = None,
    ) -> None:
        self.table_name = table_name
        self.region_name = region_name
        if dynamodb_resource:
            self._dynamodb = dynamodb_resource
        else:
            self._dynamodb = boto3.resource(
                "dynamodb",
                region_name=self.region_name,
                endpoint_url=endpoint_url,
            )
        self._table = self._dynamodb.Table(self.table_name)

    def save_event(self, event: Event) -> None:
        try:
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
            self._table.put_item(Item=item)
        except ClientError as e:
            logger.error(f"Failed to save event to DynamoDB: {e}")
            raise

    def get_events(
        self,
        person_id: str,
        limit: int = 100,
        event_type: Optional[str] = None
    ) -> List[Event]:
        try:
            response = self._table.query(
                KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
                ExpressionAttributeValues={
                    ":pk": f"PERSON#{person_id}",
                    ":sk_prefix": "EVENT#",
                },
                ScanIndexForward=False,  # latest first
                Limit=limit,
            )
            items = response.get("Items", [])
            events: List[Event] = []
            for item in items:
                if event_type and item.get("event_type") != event_type:
                    continue
                ts = datetime.fromisoformat(item["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                events.append(
                    Event(
                        event_id=item["event_id"],
                        person_id=item["person_id"],
                        event_type=EventType(item["event_type"]) if item["event_type"] in [e.value for e in EventType] else EventType.CUSTOM,
                        timestamp=ts,
                        metadata=json.loads(item["metadata"]),
                    )
                )
            return events
        except ClientError as e:
            logger.error(f"Failed to query events from DynamoDB: {e}")
            return []

    def save_reminder(self, reminder: Reminder) -> None:
        try:
            item = {
                "PK": f"PERSON#{reminder.person_id}",
                "SK": f"REMINDER#{reminder.reminder_id}",
                "reminder_id": reminder.reminder_id,
                "person_id": reminder.person_id,
                "text": reminder.text,
                "scheduled_time": reminder.scheduled_time,
                "status": reminder.status.value if hasattr(reminder.status, "value") else str(reminder.status),
                "created_at": reminder.created_at.isoformat(),
                "item_type": "REMINDER",
            }
            self._table.put_item(Item=item)
        except ClientError as e:
            logger.error(f"Failed to save reminder to DynamoDB: {e}")
            raise

    def get_reminders(
        self,
        person_id: str,
        active_only: bool = True
    ) -> List[Reminder]:
        try:
            response = self._table.query(
                KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
                ExpressionAttributeValues={
                    ":pk": f"PERSON#{person_id}",
                    ":sk_prefix": "REMINDER#",
                },
            )
            items = response.get("Items", [])
            reminders: List[Reminder] = []
            for item in items:
                if active_only and item.get("status") != ReminderStatus.PENDING.value:
                    continue
                created = datetime.fromisoformat(item["created_at"])
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                reminders.append(
                    Reminder(
                        reminder_id=item["reminder_id"],
                        person_id=item["person_id"],
                        text=item["text"],
                        scheduled_time=item["scheduled_time"],
                        status=ReminderStatus(item["status"]),
                        created_at=created,
                    )
                )
            return reminders
        except ClientError as e:
            logger.error(f"Failed to query reminders from DynamoDB: {e}")
            return []

    def save_profile(self, profile: PersonProfile) -> None:
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
            raise

    def get_profile(self, person_id: str) -> Optional[PersonProfile]:
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
            return None

    def save_alert(self, alert: Alert) -> None:
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
                "metadata": json.dumps(alert.metadata),
                "item_type": "ALERT",
            }
            self._table.put_item(Item=item)
        except ClientError as e:
            logger.error(f"Failed to save alert to DynamoDB: {e}")
            raise

    def get_alerts(
        self,
        person_id: str,
        active_only: bool = True
    ) -> List[Alert]:
        try:
            response = self._table.query(
                KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
                ExpressionAttributeValues={
                    ":pk": f"PERSON#{person_id}",
                    ":sk_prefix": "ALERT#",
                },
                ScanIndexForward=False,
            )
            items = response.get("Items", [])
            alerts: List[Alert] = []
            for item in items:
                if active_only and item.get("status") != "ACTIVE":
                    continue
                created = datetime.fromisoformat(item["created_at"])
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
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
                        metadata=json.loads(item["metadata"]),
                    )
                )
            return alerts
        except ClientError as e:
            logger.error(f"Failed to query alerts from DynamoDB: {e}")
            return []

    def save_escalation_state(self, state: EscalationState) -> None:
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
                "metadata": json.dumps(state.metadata),
                "item_type": "ESCALATION_STATE",
            }
            self._table.put_item(Item=item)
        except ClientError as e:
            logger.error(f"Failed to save escalation state to DynamoDB: {e}")
            raise

    def get_escalation_state(self, person_id: str) -> Optional[EscalationState]:
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
                metadata=json.loads(item["metadata"]),
            )
        except ClientError as e:
            logger.error(f"Failed to get escalation state from DynamoDB: {e}")
            return None

    def close(self) -> None:
        pass

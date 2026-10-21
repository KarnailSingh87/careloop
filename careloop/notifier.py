"""
Pluggable family notification system for CareLoop.

Provides:
- NotificationDeliveryStatus: Explicit lifecycle status (DELIVERED vs ACCEPTED vs FAILED).
- NotificationResult: Typed outcome of dispatch attempt with message ID, target, and carrier metadata.
- NotifierBase: Abstract interface for caregiver alerts.
- ConsoleNotifier: Local runs, terminal demonstrations, and testing.
- InMemoryNotifier: Fast in-memory spy with failure simulation for hermetic unit testing.
- SNSNotifier: Production notifications via AWS Simple Notification Service (Amazon SNS).

CRITICAL ARCHITECTURAL REALITY & NOTIFICATION TIERS:
CareLoop strictly distinguishes three tiers of alert truth:
1. Alert Created: Safety engine identifies a risk escalation or missed routine and persists
   an immutable Alert record in storage with notification_status='pending'.
2. Notification Accepted: Transport provider (e.g. AWS SNS) accepts the publish request and
   assigns a MessageId. The dispatch status is ACCEPTED (not DELIVERED).
3. Delivered to Handset: Message reached the physical phone. For SMS, this requires carrier
   delivery status receipts (via Amazon CloudWatch Logs delivery status logs). Direct publish
   to SNS only proves the request was queued by AWS, NOT that the handset received it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
import logging
import os
import re
from typing import Any, Dict, List, Optional
import uuid
import boto3
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field

from careloop.models import EmergencyContact

logger = logging.getLogger(__name__)

ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}


def mask_phone_number(phone: str) -> str:
    """Mask phone number for safe privacy-preserving logging (e.g. +1-555-***-2834)."""
    clean = phone.strip()
    if len(clean) <= 6:
        return "***"
    return f"{clean[:5]}***{clean[-4:]}"


class NotificationDeliveryStatus(str, Enum):
    """
    Explicit delivery lifecycle status for family caregiver notifications.
    
    CRITICAL DISTINCTION:
    - DELIVERED: Message was definitively delivered to recipient (e.g. console stdout or verified delivery).
    - ACCEPTED: Accepted by carrier dispatch gateway (e.g. AWS SNS returned HTTP 200 with MessageId).
      The downstream SMS carrier delivery is asynchronous and pending. It does NOT guarantee the SMS reached a phone.
    - FAILED: Transmission failed or was rejected (e.g. AWS ClientError, invalid phone number, quota exceeded).
    - SKIPPED_DEDUPLICATED: Suppressed because an identical alert was already delivered/accepted within deduplication window.
    """
    DELIVERED = "delivered"
    ACCEPTED = "accepted"
    FAILED = "failed"
    SKIPPED_DEDUPLICATED = "skipped_deduplicated"


class NotificationResult(BaseModel):
    """
    Structured outcome of a notification dispatch attempt.
    
    Evaluates to truthy in boolean expressions if dispatch was accepted or delivered:
        if result: ...
    """
    success: bool = Field(description="True if delivery was completed or accepted by provider.")
    status: NotificationDeliveryStatus = Field(description="Explicit delivery tier status.")
    message_id: Optional[str] = Field(default=None, description="Provider message ID (e.g. SNS MessageId).")
    target: Optional[str] = Field(default=None, description="Delivery target (Topic ARN or masked phone numbers).")
    error: Optional[str] = Field(default=None, description="Detailed failure or error message if failed.")
    details: Dict[str, Any] = Field(default_factory=dict, description="Provider metadata and carrier notices.")

    def __bool__(self) -> bool:
        """Allow backward-compatible boolean checking: if result: ..."""
        return self.success


class NotifierBase(ABC):
    """Abstract interface for family/caregiver notification delivery."""

    @abstractmethod
    def send_notification(
        self,
        person_id: str,
        severity: str,
        message: str,
        reasons: Optional[List[str]] = None,
        contacts: Optional[List[EmergencyContact]] = None,
        dedup_key: Optional[str] = None,
    ) -> NotificationResult:
        """
        Send an alert notification to designated family contacts.
        
        Parameters:
            person_id: Identifier of elder parent
            severity: 'low', 'medium', 'high', 'critical'
            message: Plain-English alert description
            reasons: Supporting deterministic audit reasons
            contacts: Optional list of emergency contacts
            dedup_key: Optional stable deduplication identifier
            
        Returns:
            NotificationResult: Structured delivery result with explicit status.
        """
        raise NotImplementedError


class ConsoleNotifier(NotifierBase):
    """
    Console notifier for local hackathon runs, demos, and testing.
    Outputs structured, highlighted alerts to stdout and logging.
    """

    def send_notification(
        self,
        person_id: str,
        severity: str,
        message: str,
        reasons: Optional[List[str]] = None,
        contacts: Optional[List[EmergencyContact]] = None,
        dedup_key: Optional[str] = None,
    ) -> NotificationResult:
        reasons_list = reasons or []
        contact_names = ", ".join(f"{c.name} ({mask_phone_number(c.phone)})" for c in contacts) if contacts else "Default Caregiver"

        banner = (
            f"\n{'=' * 65}\n"
            f"🚨 [CARELOOP FAMILY ALERT] Person: {person_id.upper()} | Severity: {severity.upper()}\n"
            f"Recipient(s): {contact_names}\n"
            f"Message: {message}\n"
            f"Deterministic Reasons:\n"
            + "\n".join(f"  • {r}" for r in reasons_list) + "\n"
            f"Deduplication Key: {dedup_key or 'none'}\n"
            f"{'=' * 65}\n"
        )
        print(banner)
        logger.warning(f"Family alert dispatched via ConsoleNotifier for {person_id}: {message}")

        msg_id = f"console-{uuid.uuid4().hex[:8]}"
        return NotificationResult(
            success=True,
            status=NotificationDeliveryStatus.DELIVERED,
            message_id=msg_id,
            target="console_stdout",
            details={
                "transport": "stdout",
                "reasons_count": len(reasons_list),
                "contacts_count": len(contacts or []),
                "dedup_key": dedup_key,
            },
        )


class InMemoryNotifier(NotifierBase):
    """
    In-memory notifier for testing, verification, and automated assertions.
    Records all dispatched notifications in memory.
    Supports configurable simulated failure to test retry loops.
    """

    def __init__(
        self,
        should_fail: bool = False,
        fail_error: str = "Simulated notification delivery failure",
    ) -> None:
        self.notifications: List[Dict[str, Any]] = []
        self.results: List[NotificationResult] = []
        self.should_fail = should_fail
        self.fail_error = fail_error

    def send_notification(
        self,
        person_id: str,
        severity: str,
        message: str,
        reasons: Optional[List[str]] = None,
        contacts: Optional[List[EmergencyContact]] = None,
        dedup_key: Optional[str] = None,
    ) -> NotificationResult:
        entry = {
            "person_id": person_id,
            "severity": severity,
            "message": message,
            "reasons": reasons or [],
            "contacts": contacts or [],
            "dedup_key": dedup_key,
        }
        self.notifications.append(entry)

        if self.should_fail:
            res = NotificationResult(
                success=False,
                status=NotificationDeliveryStatus.FAILED,
                error=self.fail_error,
                target="in_memory",
                details={"simulated_failure": True},
            )
            self.results.append(res)
            logger.warning(f"InMemoryNotifier simulated failure for {person_id}: {self.fail_error}")
            return res

        msg_id = f"mem-{uuid.uuid4().hex[:8]}"
        res = NotificationResult(
            success=True,
            status=NotificationDeliveryStatus.DELIVERED,
            message_id=msg_id,
            target="in_memory",
            details={
                "reasons_count": len(reasons or []),
                "contacts_count": len(contacts or []),
                "dedup_key": dedup_key,
            },
        )
        self.results.append(res)
        logger.info(f"InMemoryNotifier recorded alert for {person_id}: {message}")
        return res

    def clear(self) -> None:
        self.notifications.clear()
        self.results.clear()


class SNSNotifier(NotifierBase):
    """
    Amazon Simple Notification Service (SNS) notifier for AWS deployments.
    Publishes SMS or Topic notifications to designated caregiver phones.

    IMPORTANT ARCHITECTURAL REALITY & CARRIER HOPS:
    When boto3 client.publish() returns HTTP 200, AWS SNS has ACCEPTED the message
    and assigned an internal MessageId. The status returned is ACCEPTED, NOT DELIVERED.
    
    Downstream Carrier Factors Affecting Real Delivery:
    1. AWS SMS Sandbox: In standard new AWS accounts, messages can ONLY be delivered to
       destination phone numbers pre-verified in the AWS SNS console. Unverified numbers
       fail downstream at the carrier stage without raising a publish exception.
    2. Origination Identity & 10DLC: In the US and Canada, carrier regulations require a registered
       10DLC (10-Digit Long Code) campaign, Toll-Free Number, or Short Code. Unregistered long
       codes are subject to carrier spam filtering and throttling.
    3. Regional Regulations: India requires TRAI DLT registration; UK/EU requires approved Alpha Sender IDs.
    4. Destination Opt-Outs: If a caregiver replied 'STOP', AWS SNS blacklists the destination phone.
    5. Delivery Status Verification: Authoritative handset delivery confirmation requires configuring
       SNS Delivery Status Logging to Amazon CloudWatch Logs (IAM role DirectPublishToPhoneNumber).
    6. Billing & Costs: SMS charges apply per message segment (160 GSM-7 / 70 UCS-2 characters)
       regardless of whether the handset was reachable.
    """

    def __init__(
        self,
        topic_arn: Optional[str] = None,
        region_name: str = "us-east-1",
        sns_client: Optional[Any] = None,
    ) -> None:
        self.topic_arn = topic_arn or os.getenv("SNS_TOPIC_ARN")
        self.region_name = region_name or os.getenv("AWS_REGION", "us-east-1")
        self._sns_client = sns_client

    def _get_client(self) -> Any:
        if self._sns_client is None:
            self._sns_client = boto3.client("sns", region_name=self.region_name)
        return self._sns_client

    def send_notification(
        self,
        person_id: str,
        severity: str,
        message: str,
        reasons: Optional[List[str]] = None,
        contacts: Optional[List[EmergencyContact]] = None,
        dedup_key: Optional[str] = None,
    ) -> NotificationResult:
        # Validate inputs
        if not person_id or not person_id.strip():
            return NotificationResult(
                success=False,
                status=NotificationDeliveryStatus.FAILED,
                error="Person identifier cannot be empty.",
            )
        sev = severity.strip().lower()
        if sev not in ALLOWED_SEVERITIES:
            return NotificationResult(
                success=False,
                status=NotificationDeliveryStatus.FAILED,
                error=f"Unsupported severity '{severity}'. Allowed values: {', '.join(sorted(ALLOWED_SEVERITIES))}",
            )
        if not message or not message.strip():
            return NotificationResult(
                success=False,
                status=NotificationDeliveryStatus.FAILED,
                error="Notification message cannot be empty.",
            )

        client = self._get_client()
        reasons_str = "\n".join(f"- {r}" for r in (reasons or []))
        full_message = (
            f"[CareLoop Alert - {sev.upper()}]\n"
            f"Alert for {person_id.capitalize()}:\n"
            f"{message.strip()}\n\n"
            f"Reasons:\n{reasons_str}"
        )
        if dedup_key:
            full_message += f"\n\nRef: {dedup_key}"

        try:
            # 1. If Topic ARN is configured, publish to Topic (Fan-out)
            if self.topic_arn:
                response = client.publish(
                    TopicArn=self.topic_arn,
                    Subject=f"CareLoop Alert: {person_id.capitalize()} ({sev.upper()})",
                    Message=full_message,
                )
                msg_id = response.get("MessageId", str(uuid.uuid4()))
                logger.info(f"Published alert to SNS Topic {self.topic_arn} (MessageId={msg_id})")
                return NotificationResult(
                    success=True,
                    status=NotificationDeliveryStatus.ACCEPTED,
                    message_id=msg_id,
                    target=self.topic_arn,
                    details={
                        "type": "sns_topic",
                        "topic_arn": self.topic_arn,
                        "reasons_count": len(reasons or []),
                        "carrier_note": "Alert published to SNS Topic. Fan-out delivery managed by SNS subscriptions.",
                    },
                )

            # 2. Otherwise send direct SMS to contacts if phone numbers are available
            if contacts:
                phone_contacts = [c for c in contacts if c.phone and c.phone.strip()]
                if not phone_contacts:
                    return NotificationResult(
                        success=False,
                        status=NotificationDeliveryStatus.FAILED,
                        error="Emergency contacts configured, but no valid phone numbers present.",
                    )

                published_ids = []
                masked_phones = []
                for contact in phone_contacts:
                    phone = contact.phone.strip()
                    res = client.publish(
                        PhoneNumber=phone,
                        Message=full_message[:160],  # SMS brevity per segment
                    )
                    m_id = res.get("MessageId", str(uuid.uuid4()))
                    published_ids.append(m_id)
                    masked = mask_phone_number(phone)
                    masked_phones.append(masked)
                    logger.info(f"Published direct SMS alert to {masked} (MessageId={m_id})")

                primary_id = published_ids[0] if published_ids else str(uuid.uuid4())
                return NotificationResult(
                    success=True,
                    status=NotificationDeliveryStatus.ACCEPTED,
                    message_id=primary_id,
                    target=", ".join(masked_phones),
                    details={
                        "type": "direct_sms",
                        "all_message_ids": published_ids,
                        "recipients": masked_phones,
                        "sms_count": len(published_ids),
                        "carrier_note": (
                            "SMS accepted by AWS SNS. Delivery to recipient handset is pending carrier "
                            "transmission and is subject to AWS SMS Sandbox verification, carrier 10DLC/DLT "
                            "origination registration, and recipient opt-out status."
                        ),
                    },
                )

            # Fallback publish without target
            logger.warning("SNSNotifier: Neither SNS_TOPIC_ARN nor contact phone available.")
            return NotificationResult(
                success=False,
                status=NotificationDeliveryStatus.FAILED,
                error="Neither SNS_TOPIC_ARN nor emergency contact phone numbers are configured.",
            )

        except ClientError as e:
            err_code = e.response.get("Error", {}).get("Code", "ClientError")
            err_msg = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"SNS publish failed [{err_code}]: {err_msg}")
            return NotificationResult(
                success=False,
                status=NotificationDeliveryStatus.FAILED,
                error=f"SNS publish failed [{err_code}]: {err_msg}",
                details={"error_code": err_code},
            )
        except Exception as e:
            logger.error(f"SNS publish unexpected exception: {e}")
            return NotificationResult(
                success=False,
                status=NotificationDeliveryStatus.FAILED,
                error=f"SNS publish unexpected error: {str(e)}",
            )


def get_default_notifier() -> NotifierBase:
    """Factory selecting notifier based on NOTIFIER_TYPE env var."""
    notifier_type = os.getenv("NOTIFIER_TYPE", "console").lower()
    if notifier_type == "sns":
        return SNSNotifier()
    return ConsoleNotifier()


__all__ = [
    "ALLOWED_SEVERITIES",
    "mask_phone_number",
    "NotificationDeliveryStatus",
    "NotificationResult",
    "NotifierBase",
    "ConsoleNotifier",
    "InMemoryNotifier",
    "SNSNotifier",
    "get_default_notifier",
]

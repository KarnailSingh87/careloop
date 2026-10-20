"""
Pluggable family notification system for CareLoop.

Provides:
- NotifierBase: Abstract interface for caregiver alerts
- ConsoleNotifier: Local runs, terminal demonstrations, and testing
- SNSNotifier: Production notifications via AWS Simple Notification Service (Amazon SNS)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
import os
from typing import Any, Dict, List, Optional
import boto3
from botocore.exceptions import ClientError

from careloop.models import EmergencyContact

logger = logging.getLogger(__name__)


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
    ) -> bool:
        """
        Send an alert notification to designated family contacts.
        
        Parameters:
            person_id: Identifier of elder parent
            severity: 'low', 'medium', 'high', 'critical'
            message: Plain-English alert description
            reasons: Supporting deterministic audit reasons
            contacts: Optional list of emergency contacts
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
    ) -> bool:
        reasons_list = reasons or []
        contact_names = ", ".join(f"{c.name} ({c.phone})" for c in contacts) if contacts else "Default Caregiver"

        banner = (
            f"\n{'=' * 65}\n"
            f"🚨 [CARELOOP FAMILY ALERT] Person: {person_id.upper()} | Severity: {severity.upper()}\n"
            f"Recipient(s): {contact_names}\n"
            f"Message: {message}\n"
            f"Deterministic Reasons:\n"
            + "\n".join(f"  • {r}" for r in reasons_list) + "\n"
            f"{'=' * 65}\n"
        )
        print(banner)
        logger.warning(f"Family alert dispatched via ConsoleNotifier for {person_id}: {message}")
        return True


class SNSNotifier(NotifierBase):
    """
    Amazon Simple Notification Service (SNS) notifier for AWS deployments.
    Publishes SMS or Topic notifications to designated caregiver phones.
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
    ) -> bool:
        client = self._get_client()
        reasons_str = "\n".join(f"- {r}" for r in (reasons or []))
        full_message = (
            f"[CareLoop Alert - {severity.upper()}]\n"
            f"Alert for {person_id.capitalize()}:\n"
            f"{message}\n\n"
            f"Reasons:\n{reasons_str}"
        )

        try:
            # 1. If Topic ARN is configured, publish to Topic
            if self.topic_arn:
                client.publish(
                    TopicArn=self.topic_arn,
                    Subject=f"CareLoop Alert: {person_id.capitalize()} ({severity.upper()})",
                    Message=full_message,
                )
                logger.info(f"Published alert to SNS Topic {self.topic_arn}")
                return True

            # 2. Otherwise send direct SMS to contacts if phones are available
            if contacts:
                for contact in contacts:
                    if contact.phone:
                        client.publish(
                            PhoneNumber=contact.phone,
                            Message=full_message[:160],  # SMS brevity
                        )
                        logger.info(f"Published direct SMS alert to {contact.phone}")
                return True

            # Fallback publish without target
            logger.warning("SNSNotifier: Neither SNS_TOPIC_ARN nor contact phone available.")
            return False

        except ClientError as e:
            logger.error(f"SNS publish failed: {e}")
            return False


def get_default_notifier() -> NotifierBase:
    """Factory selecting notifier based on NOTIFIER_TYPE env var."""
    notifier_type = os.getenv("NOTIFIER_TYPE", "console").lower()
    if notifier_type == "sns":
        return SNSNotifier()
    return ConsoleNotifier()

"""
Unit tests for CareLoop pluggable notifiers (careloop/notifier.py).
"""

from unittest.mock import MagicMock
import pytest
from botocore.exceptions import ClientError

from careloop.models import EmergencyContact
from careloop.notifier import ConsoleNotifier, SNSNotifier, get_default_notifier


def test_console_notifier():
    notifier = ConsoleNotifier()
    contact = EmergencyContact(
        name="Linda Davis",
        relationship="Daughter",
        phone="+1-555-019-2834",
    )
    success = notifier.send_notification(
        person_id="eleanor",
        severity="high",
        message="Missed medication check-in timeout.",
        reasons=["Medication expected at 08:30 UTC", "No response to voice check-in"],
        contacts=[contact],
    )
    assert success is True


def test_sns_notifier_with_topic():
    mock_sns = MagicMock()
    mock_sns.publish.return_value = {"MessageId": "msg-12345"}

    notifier = SNSNotifier(
        topic_arn="arn:aws:sns:us-east-1:123456789012:CareLoopAlerts",
        sns_client=mock_sns,
    )

    success = notifier.send_notification(
        person_id="eleanor",
        severity="critical",
        message="Unresponsive check-in.",
        reasons=["Repeat voice prompt timed out."],
    )

    assert success is True
    mock_sns.publish.assert_called_once()
    call_kwargs = mock_sns.publish.call_args.kwargs
    assert call_kwargs["TopicArn"] == "arn:aws:sns:us-east-1:123456789012:CareLoopAlerts"
    assert "Unresponsive check-in" in call_kwargs["Message"]


def test_sns_notifier_direct_sms():
    mock_sns = MagicMock()
    mock_sns.publish.return_value = {"MessageId": "sms-123"}

    notifier = SNSNotifier(
        topic_arn=None,
        sns_client=mock_sns,
    )
    contact = EmergencyContact(
        name="Linda Davis",
        relationship="Daughter",
        phone="+1-555-019-2834",
    )

    success = notifier.send_notification(
        person_id="eleanor",
        severity="high",
        message="Check-in timeout.",
        contacts=[contact],
    )

    assert success is True
    mock_sns.publish.assert_called_once()
    call_kwargs = mock_sns.publish.call_args.kwargs
    assert call_kwargs["PhoneNumber"] == "+1-555-019-2834"


def test_sns_notifier_error_handling():
    mock_sns = MagicMock()
    mock_sns.publish.side_effect = ClientError(
        {"Error": {"Code": "InvalidParameter", "Message": "Bad ARN"}},
        "Publish",
    )

    notifier = SNSNotifier(
        topic_arn="arn:aws:sns:invalid",
        sns_client=mock_sns,
    )
    success = notifier.send_notification(
        person_id="eleanor",
        severity="high",
        message="Test alert",
    )
    assert success is False

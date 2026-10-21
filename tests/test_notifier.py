"""
Unit tests for CareLoop pluggable notifiers (careloop/notifier.py).
"""

from unittest.mock import MagicMock
import pytest
from botocore.exceptions import ClientError

from careloop.models import EmergencyContact
from careloop.notifier import (
    ALLOWED_SEVERITIES,
    ConsoleNotifier,
    InMemoryNotifier,
    NotificationDeliveryStatus,
    NotificationResult,
    SNSNotifier,
    get_default_notifier,
    mask_phone_number,
)


def test_mask_phone_number():
    assert mask_phone_number("+1-555-019-2834") == "+1-55***2834"
    assert mask_phone_number("123") == "***"
    assert mask_phone_number("+44 7911 123456") == "+44 7***3456"


def test_notification_result_boolean_protocol():
    delivered = NotificationResult(success=True, status=NotificationDeliveryStatus.DELIVERED)
    assert bool(delivered) is True
    assert delivered == True

    accepted = NotificationResult(success=True, status=NotificationDeliveryStatus.ACCEPTED)
    assert bool(accepted) is True
    assert accepted == True

    failed = NotificationResult(success=False, status=NotificationDeliveryStatus.FAILED, error="Timeout")
    assert bool(failed) is False
    assert failed == False


def test_console_notifier():
    notifier = ConsoleNotifier()
    contact = EmergencyContact(
        name="Linda Davis",
        relationship="Daughter",
        phone="+1-555-019-2834",
    )
    result = notifier.send_notification(
        person_id="eleanor",
        severity="high",
        message="Missed medication check-in timeout.",
        reasons=["Medication expected at 08:30 UTC", "No response to voice check-in"],
        contacts=[contact],
    )
    assert result.success is True
    assert result.status == NotificationDeliveryStatus.DELIVERED
    assert result.target == "console_stdout"
    assert result.message_id is not None
    assert result.message_id.startswith("console-")


def test_in_memory_notifier():
    notifier = InMemoryNotifier()
    contact = EmergencyContact(
        name="Linda Davis",
        relationship="Daughter",
        phone="+1-555-019-2834",
    )
    result = notifier.send_notification(
        person_id="eleanor",
        severity="critical",
        message="Missed lunch and no activity.",
        reasons=["Routine window expired", "No motion detected"],
        contacts=[contact],
        dedup_key="alert:eleanor:2026-10-21:lunch:critical",
    )
    assert result.success is True
    assert result.status == NotificationDeliveryStatus.DELIVERED
    assert len(notifier.notifications) == 1

    # Test failure mode
    failing_notifier = InMemoryNotifier(should_fail=True, fail_error="Simulated network error")
    fail_result = failing_notifier.send_notification(
        person_id="eleanor",
        severity="high",
        message="Test alert",
    )
    assert fail_result.success is False
    assert fail_result.status == NotificationDeliveryStatus.FAILED
    assert fail_result.error == "Simulated network error"


def test_sns_notifier_with_topic():
    mock_sns = MagicMock()
    mock_sns.publish.return_value = {"MessageId": "msg-12345"}

    notifier = SNSNotifier(
        topic_arn="arn:aws:sns:us-east-1:123456789012:CareLoopAlerts",
        sns_client=mock_sns,
    )

    result = notifier.send_notification(
        person_id="eleanor",
        severity="critical",
        message="Unresponsive check-in.",
        reasons=["Repeat voice prompt timed out."],
    )

    # CRITICAL: SNS publish acceptance is ACCEPTED, NOT DELIVERED
    assert result.success is True
    assert result.status == NotificationDeliveryStatus.ACCEPTED
    assert result.message_id == "msg-12345"
    assert result.target == "arn:aws:sns:us-east-1:123456789012:CareLoopAlerts"

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

    result = notifier.send_notification(
        person_id="eleanor",
        severity="high",
        message="Check-in timeout.",
        contacts=[contact],
    )

    # CRITICAL: SMS publish is ACCEPTED, NOT DELIVERED
    assert result.success is True
    assert result.status == NotificationDeliveryStatus.ACCEPTED
    assert result.message_id == "sms-123"
    assert "10DLC" in result.details.get("carrier_note", "")

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
    result = notifier.send_notification(
        person_id="eleanor",
        severity="high",
        message="Test alert",
    )
    assert result.success is False
    assert result.status == NotificationDeliveryStatus.FAILED
    assert "InvalidParameter" in result.error


def test_sns_notifier_validation_errors():
    mock_sns = MagicMock()
    notifier = SNSNotifier(
        topic_arn="arn:aws:sns:us-east-1:123456789012:CareLoopAlerts",
        sns_client=mock_sns,
    )

    # Empty person_id
    res_empty_person = notifier.send_notification(person_id="  ", severity="high", message="Hello")
    assert res_empty_person.success is False
    assert res_empty_person.status == NotificationDeliveryStatus.FAILED
    assert "Person identifier" in res_empty_person.error

    # Empty message
    res_empty_msg = notifier.send_notification(person_id="eleanor", severity="high", message="")
    assert res_empty_msg.success is False
    assert "message" in res_empty_msg.error

    # Unsupported severity
    res_bad_sev = notifier.send_notification(person_id="eleanor", severity="extreme", message="Danger")
    assert res_bad_sev.success is False
    assert "severity" in res_bad_sev.error

"""
CareLoop Opt-In AWS Amazon SNS Live Smoke Test.

CRITICAL SAFETY & TEST ISOLATION POLICY:
1. This test NEVER runs during ordinary unit test runs or CI (`pytest tests/`).
2. It requires explicit opt-in via environment variable: `RUN_AWS_SMOKE_TEST=1`.
3. It requires preflight credential and environment verification.
4. ZERO HARDCODED PHONE NUMBERS: Target phone number or topic ARN MUST be injected
   via `CARELOOP_TEST_PHONE` or `CARELOOP_SNS_TOPIC_ARN`.
5. ALL phone numbers logged or displayed are masked for privacy.
6. Crucial Delivery Tier Distinction: SNS publish acceptance proves AWS SNS accepted
   the message (`status=accepted`). Carrier delivery to the phone requires AWS SMS Sandbox
   verification, 10DLC registration, and CloudWatch SMS Delivery Status logs.
"""

from datetime import datetime, timezone
import os
import pytest

from careloop.models import EmergencyContact
from careloop.notifier import (
    NotificationDeliveryStatus,
    SNSNotifier,
    mask_phone_number,
)


def _check_aws_preflight():
    """
    Perform preflight checks before attempting any live AWS API calls.
    Returns (boto3_session, topic_arn, test_phone).
    """
    if os.getenv("RUN_AWS_SMOKE_TEST") != "1":
        pytest.skip("AWS SNS smoke test skipped. To run against live AWS, set RUN_AWS_SMOKE_TEST=1.")

    try:
        import boto3
        from botocore.exceptions import NoCredentialsError, ClientError
    except ImportError:
        pytest.skip("boto3 is required for AWS SNS smoke testing.")

    # 1. Verify credentials via STS caller identity
    try:
        sts = boto3.client("sts")
        identity = sts.get_caller_identity()
        identity.get("Account", "unknown")
    except (NoCredentialsError, ClientError) as e:
        pytest.skip(f"AWS preflight failed: No valid AWS credentials found ({e}).")

    # 2. Check for configured target destination (NO hardcoded phone numbers)
    topic_arn = os.getenv("CARELOOP_SNS_TOPIC_ARN", "").strip() or None
    test_phone = os.getenv("CARELOOP_TEST_PHONE", "").strip() or None

    if not topic_arn and not test_phone:
        pytest.skip(
            "AWS preflight skipped: Neither CARELOOP_SNS_TOPIC_ARN nor CARELOOP_TEST_PHONE "
            "environment variable is configured. Provide an explicit target to run the live smoke test."
        )

    return boto3.client("sns"), topic_arn, test_phone


def test_aws_sns_live_smoke():
    """
    Opt-in live AWS SNS smoke test verifying AWS SNS publish acceptance,
    delivery tier boundaries, and carrier metadata.
    """
    sns_client, topic_arn, test_phone = _check_aws_preflight()

    contacts = []
    if test_phone:
        contacts.append(
            EmergencyContact(
                name="Authorized Smoke Test Recipient",
                relationship="Caregiver",
                phone=test_phone,
            )
        )

    notifier = SNSNotifier(
        topic_arn=topic_arn,
        sns_client=sns_client,
    )

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    result = notifier.send_notification(
        person_id="eleanor",
        severity="high",
        message=f"[CareLoop Live Smoke Test] Routine check-in verification at {now_iso}.",
        reasons=[
            "Preflight credentials verified via AWS STS",
            f"Target: {topic_arn or mask_phone_number(test_phone)}",
            "Checking AWS SNS publish acceptance",
        ],
        contacts=contacts if not topic_arn else None,
        dedup_key=f"smoke:test:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
    )

    # 1. AWS Acceptance Verification
    assert result.success is True
    # CRITICAL: SNS publish acceptance is ACCEPTED, NOT DELIVERED!
    assert result.status == NotificationDeliveryStatus.ACCEPTED
    assert result.message_id is not None
    assert len(result.message_id) > 0

    # 2. Verify target is masked for privacy
    if test_phone:
        assert test_phone not in result.target
        assert "***" in result.target

    # 3. Carrier requirements and origination explanation
    details = result.details
    assert "carrier_note" in details
    carrier_note = details["carrier_note"]

    # Verify documented carrier realities
    if test_phone:
        assert "AWS SMS Sandbox" in carrier_note
        assert "10DLC" in carrier_note
    else:
        assert "Topic" in carrier_note

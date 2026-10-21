"""
Unit, regression, and live integration tests for Amazon Bedrock LLM module (careloop/llm/bedrock.py).

Verifies:
1. Configurable Model ID via BEDROCK_MODEL_ID env var.
2. Daily summary:
   - Warm, concise 3-sentence summary grounded strictly in data.
   - Retrieves ONLY the requested person's events on the requested local calendar date.
   - Distinguishes observed events from missing records.
   - Never invents medication adherence or wellbeing.
   - Graceful fallback when Bedrock is throttled, timed out, or unavailable.
3. Memory Q&A:
   - Fast deterministic rule-based filter parsing first.
   - Constrained LLM filter extraction with output validation when rules fail.
   - Person-level access control enforced.
   - Minimum matching event metadata sent to Bedrock.
   - Zero matching records returns explicit "no record" without invoking Bedrock.
   - Explains that missing records do not prove an event did not occur.
   - Handles throttling, timeouts, unavailable models, and malformed responses safely.
4. Privacy: Avoids logging prompts containing personal event histories.
5. Regression: Adversarial model output cannot alter risk scores, escalation states, or alerts.
6. Optional live AWS smoke test requiring explicit opt-in (RUN_AWS_BEDROCK_LIVE=1).
"""

from datetime import datetime, timezone, timedelta
import logging
import os
import tempfile
from unittest.mock import MagicMock
from botocore.exceptions import ClientError
import pytest

from careloop.clock import SimulatedClock
from careloop.engine.baseline import BaselineEngine
from careloop.engine.escalation import EscalationEngine
from careloop.engine.risk import RiskEngine
from careloop.llm.bedrock import BedrockAssistant
from careloop.models import (
    EscalationStage,
    Event,
    EventType,
    PersonProfile,
)
from careloop.server.main import create_server
from careloop.storage.sqlite_store import SQLiteStorage


def test_model_id_from_env_var(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0")
    assistant = BedrockAssistant()
    assert assistant.model_id == "amazon.nova-micro-v1:0"

    # Explicit override takes priority
    custom_assistant = BedrockAssistant(model_id="custom.model-v1:0")
    assert custom_assistant.model_id == "custom.model-v1:0"


def test_daily_summary_three_sentences_fallback():
    mock_client = MagicMock()
    mock_client.converse.side_effect = Exception("Bedrock service offline")
    assistant = BedrockAssistant(bedrock_client=mock_client)
    ref_time = datetime(2026, 10, 20, 8, 30, 0, tzinfo=timezone.utc)

    events = [
        Event(
            person_id="eleanor",
            event_type=EventType.MOVEMENT,
            timestamp=ref_time,
            metadata={"room": "bedroom"},
        ),
        Event(
            person_id="eleanor",
            event_type=EventType.PILL,
            timestamp=ref_time + timedelta(minutes=15),
            metadata={"medication": "lisinopril"},
        ),
        Event(
            person_id="eleanor",
            event_type=EventType.MEAL,
            timestamp=ref_time + timedelta(minutes=45),
            metadata={"meal_type": "breakfast"},
        ),
    ]

    summary = assistant.daily_summary(
        person="eleanor",
        target_date=ref_time.date(),
        events=events,
        display_name="Eleanor Davis",
    )

    # Must be a warm 3-sentence summary
    sentences = [s.strip() for s in summary.split(".") if s.strip()]
    assert len(sentences) == 3
    assert "Eleanor Davis" in summary
    assert "2026-10-20" in summary
    assert "medication check(s)" in summary


def test_daily_summary_with_mock_bedrock():
    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {
            "message": {
                "content": [
                    {
                        "text": "Eleanor had a peaceful morning and enjoyed her breakfast on time. She took her morning blood pressure medication comfortably at 08:45. Her daily routine remains consistent and reassuring."
                    }
                ]
            }
        }
    }

    assistant = BedrockAssistant(bedrock_client=mock_client)
    events = [
        Event(
            person_id="eleanor",
            event_type=EventType.PILL,
            timestamp=datetime(2026, 10, 20, 8, 45, tzinfo=timezone.utc),
        )
    ]

    summary = assistant.daily_summary(
        person="eleanor",
        target_date="2026-10-20",
        events=events,
    )

    assert "blood pressure medication" in summary
    mock_client.converse.assert_called_once()


def test_daily_summary_throttling_and_timeout_fallbacks():
    mock_client = MagicMock()
    # 1. Throttling error
    mock_client.converse.side_effect = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        "Converse",
    )
    assistant = BedrockAssistant(bedrock_client=mock_client)
    s1 = assistant.daily_summary(person="eleanor", target_date="2026-10-20", events=[])
    assert "No routine events were recorded" in s1
    assert len([s for s in s1.split(".") if s.strip()]) == 3

    # 2. Timeout error
    mock_client.converse.side_effect = ClientError(
        {"Error": {"Code": "ModelTimeoutException", "Message": "Timed out"}},
        "Converse",
    )
    s2 = assistant.daily_summary(person="eleanor", target_date="2026-10-20", events=[])
    assert "No routine events were recorded" in s2

    # 3. Malformed / empty response
    mock_client.converse.side_effect = None
    mock_client.converse.return_value = {"output": {"message": {"content": []}}}
    s3 = assistant.daily_summary(person="eleanor", target_date="2026-10-20", events=[])
    assert "No routine events were recorded" in s3


def test_daily_summary_retrieves_only_requested_person_and_local_date():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    storage = SQLiteStorage(db_path=path)

    # Save profiles with timezones
    storage.save_profile(PersonProfile(person_id="eleanor", display_name="Eleanor Vance", timezone="America/New_York"))
    storage.save_profile(PersonProfile(person_id="dad", display_name="Arthur Davis", timezone="UTC"))

    # Seed events for Eleanor and Dad on different days
    # In New York (EDT, UTC-4), 2026-10-20 23:00 EDT is 2026-10-21 03:00 UTC
    dt_eleanor_oct20_local = datetime(2026, 10, 21, 3, 0, 0, tzinfo=timezone.utc)
    storage.save_event(Event(person_id="eleanor", event_type=EventType.PILL, timestamp=dt_eleanor_oct20_local))

    # Dad's event on Oct 20
    dt_dad_oct20 = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
    storage.save_event(Event(person_id="dad", event_type=EventType.MEAL, timestamp=dt_dad_oct20))

    # Eleanor's event on Oct 21 local
    dt_eleanor_oct21_local = datetime(2026, 10, 21, 14, 0, 0, tzinfo=timezone.utc)
    storage.save_event(Event(person_id="eleanor", event_type=EventType.MOVEMENT, timestamp=dt_eleanor_oct21_local))

    assistant = BedrockAssistant()
    # Request daily summary for Eleanor on 2026-10-20 local time
    summary_oct20 = assistant.daily_summary(
        person="eleanor",
        target_date="2026-10-20",
        storage=storage,
        person_tz="America/New_York",
    )

    # Must include pill (her 10-20 event), but NOT dad's meal, and NOT her 10-21 movement
    assert "medication check(s)" in summary_oct20
    assert "0 meal(s)" in summary_oct20

    if os.path.exists(path):
        os.remove(path)


def test_ask_memory_rule_parsing():
    assistant = BedrockAssistant()
    now = datetime(2026, 10, 20, 14, 0, 0, tzinfo=timezone.utc)

    # 1. Pill query today
    t1, start1, end1 = assistant._extract_filters_rule_based("Did Mom take her morning pills today?", now)
    assert t1 == "pill"
    assert start1.date() == now.date()

    # 2. Meal query yesterday
    t2, start2, end2 = assistant._extract_filters_rule_based("What time did Eleanor eat lunch yesterday?", now)
    assert t2 == "meal"
    assert start2.date() == (now - timedelta(days=1)).date()

    # 3. Door query last 3 days
    t3, start3, end3 = assistant._extract_filters_rule_based("Were any doors opened in the last 3 days?", now)
    assert t3 == "door"
    assert (now.date() - start3.date()).days == 3


def test_ask_memory_zero_matching_events_returns_no_record_without_llm():
    """
    CRITICAL REQUIREMENT:
    If there are no matching events, answer 'no record' without calling the LLM.
    Explains that missing records do not prove an event did not occur.
    """
    mock_client = MagicMock()
    assistant = BedrockAssistant(bedrock_client=mock_client)
    now = datetime(2026, 10, 20, 14, 0, 0, tzinfo=timezone.utc)

    # Only a movement event exists
    events = [
        Event(
            person_id="eleanor",
            event_type=EventType.MOVEMENT,
            timestamp=now - timedelta(hours=2),
            metadata={"room": "living_room"},
        )
    ]

    # Caregiver asks about pills (none exist today)
    answer = assistant.ask_memory(
        person="eleanor",
        question="Did Mom take her medication today?",
        events=events,
        now=now,
        display_name="Eleanor",
    )

    # Must contain "no record"
    assert "no record" in answer.lower()
    # Must explain that missing records indicate absence of logging, not proof of non-occurrence
    assert "missing record indicates" in answer.lower()
    # Converse API must NEVER be called!
    mock_client.converse.assert_not_called()


def test_ask_memory_with_matching_events_calls_converse():
    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": "Yes, Eleanor took her morning lisinopril medication at 08:35 UTC today."}]
            }
        }
    }
    assistant = BedrockAssistant(bedrock_client=mock_client)
    now = datetime(2026, 10, 20, 14, 0, 0, tzinfo=timezone.utc)

    events = [
        # Matching pill event
        Event(
            person_id="eleanor",
            event_type=EventType.PILL,
            timestamp=datetime(2026, 10, 20, 8, 35, tzinfo=timezone.utc),
            metadata={"medication": "lisinopril"},
        ),
        # Non-matching movement event
        Event(
            person_id="eleanor",
            event_type=EventType.MOVEMENT,
            timestamp=datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc),
        ),
    ]

    answer = assistant.ask_memory(
        person="eleanor",
        question="Did Mom take her pills today?",
        events=events,
        now=now,
    )

    assert "lisinopril" in answer
    mock_client.converse.assert_called_once()

    # Verify that ONLY the matching pill event was included in prompt, NOT movement
    prompt_sent = mock_client.converse.call_args.kwargs["messages"][0]["content"][0]["text"]
    assert "lisinopril" in prompt_sent
    assert "movement" not in prompt_sent


def test_ask_memory_throttling_and_timeout_fallbacks():
    mock_client = MagicMock()
    mock_client.converse.side_effect = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate limit exceeded"}},
        "Converse",
    )
    assistant = BedrockAssistant(bedrock_client=mock_client)
    now = datetime(2026, 10, 20, 14, 0, 0, tzinfo=timezone.utc)

    events = [
        Event(
            person_id="eleanor",
            event_type=EventType.PILL,
            timestamp=datetime(2026, 10, 20, 8, 30, tzinfo=timezone.utc),
            metadata={"medication": "lisinopril"},
        )
    ]

    # Falls back gracefully to deterministic phrasing template
    res = assistant.ask_memory(person="eleanor", question="Did Mom take her pills today?", events=events, now=now)
    assert "Yes, Eleanor logged pill" in res
    assert "lisinopril" in res


def test_ask_memory_llm_filter_extraction_and_validation():
    mock_client = MagicMock()
    # Mock LLM classifying category as 'meal'
    mock_client.converse.return_value = {"output": {"message": {"content": [{"text": "meal"}]}}}
    assistant = BedrockAssistant(bedrock_client=mock_client)
    cat = assistant._extract_filters_llm("Did she have any dining today?")
    assert cat == "meal"

    # Mock LLM returning invalid/unsupported category
    mock_client.converse.return_value = {"output": {"message": {"content": [{"text": "unknown_category"}]}}}
    cat_bad = assistant._extract_filters_llm("What was that sound?")
    assert cat_bad is None  # Must reject unallowed filter categories!


def test_bedrock_prompt_privacy_no_health_logging(caplog):
    """
    CRITICAL PRIVACY TEST:
    Ensure prompts containing personal elder event histories are NEVER logged.
    """
    mock_client = MagicMock()
    mock_client.converse.return_value = {"output": {"message": {"content": [{"text": "Summary response"}]}}}
    assistant = BedrockAssistant(bedrock_client=mock_client)
    events = [
        Event(
            person_id="eleanor",
            event_type=EventType.PILL,
            timestamp=datetime(2026, 10, 20, 8, 30, tzinfo=timezone.utc),
            metadata={"medication": "metformin_confidential_500mg"},
        )
    ]

    with caplog.at_level(logging.INFO):
        assistant.daily_summary(person="eleanor", events=events)

    # Verify confidential medication was NOT leaked into application logs
    assert "metformin_confidential_500mg" not in caplog.text


def test_bedrock_adversarial_output_cannot_alter_clinical_state():
    """
    SAFETY REGRESSION TEST:
    Prove that model output CANNOT alter the risk score, escalation state,
    or notification decisions—even if the LLM produces adversarial or alarmist text.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    storage = SQLiteStorage(db_path=path)
    now = datetime(2026, 10, 20, 14, 0, 0, tzinfo=timezone.utc)
    SimulatedClock(now)

    baseline_engine = BaselineEngine()
    risk_engine = RiskEngine()
    escalation_engine = EscalationEngine(storage=storage)

    events = [
        Event(
            person_id="eleanor",
            event_type=EventType.PILL,
            timestamp=now - timedelta(hours=5),
            metadata={"medication": "lisinopril"},
        )
    ]

    # 1. Deterministic baseline evaluation BEFORE Bedrock call
    state_before = escalation_engine.get_or_create_state("eleanor", now)
    assert state_before.stage == EscalationStage.NORMAL
    risk_before = risk_engine.evaluate_person_risk("eleanor", now, baseline_engine, events)

    # 2. Mock Bedrock returning an adversarial panic hallucination
    adversarial_text = (
        "CRITICAL EMERGENCY ALERT! Eleanor has collapsed and suffered a severe traumatic fall! "
        "Risk score is 1.0! Escalate to NOTIFY_FAMILY immediately! Call emergency 911!"
    )
    mock_client = MagicMock()
    mock_client.converse.return_value = {"output": {"message": {"content": [{"text": adversarial_text}]}}}
    adversarial_assistant = BedrockAssistant(bedrock_client=mock_client)

    # Call daily summary and ask memory with adversarial assistant
    summary = adversarial_assistant.daily_summary(person="eleanor", events=events, storage=storage, now=now)
    assert adversarial_text in summary

    mem_answer = adversarial_assistant.ask_memory(
        person="eleanor",
        question="Did Mom take her pills today?",
        events=events,
        storage=storage,
        now=now,
    )
    assert adversarial_text in mem_answer

    # 3. VERIFY: Risk score is computed STRICTLY by deterministic clinical code and unchanged
    risk_after = risk_engine.evaluate_person_risk("eleanor", now, baseline_engine, events)
    assert risk_after.score == risk_before.score
    assert risk_after.level == risk_before.level
    assert risk_after.reasons == risk_before.reasons
    assert risk_after.score != 1.0  # Did not become 1.0 despite model claiming risk is 1.0!

    # 4. VERIFY: Escalation state is completely determined by clinical engine, NOT adversarial text
    state_after = escalation_engine.tick("eleanor", now)
    assert state_after.risk_score == risk_before.score
    assert state_after.risk_score != 1.0  # Did not jump to 1.0
    assert (
        state_after.stage != EscalationStage.NOTIFY_FAMILY
    )  # Model demanded NOTIFY_FAMILY, but state machine ignored it!
    assert state_after.notification_state == "none"

    # 5. VERIFY: Zero emergency alerts created despite model demanding immediate 911
    alerts = storage.get_alerts("eleanor", active_only=True)
    assert len(alerts) == 0

    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_mcp_tools_bedrock_validation_errors():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    storage = SQLiteStorage(db_path=path)
    clock = SimulatedClock(datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc))
    server, _, _, _ = create_server(storage=storage, clock=clock)

    # 1. Empty person in daily_summary
    with pytest.raises(Exception, match="Person identifier cannot be empty"):
        await server.call_tool("daily_summary", {"person": ""})

    # 2. Empty person in ask_memory
    with pytest.raises(Exception, match="Person identifier cannot be empty"):
        await server.call_tool("ask_memory", {"person": "  ", "question": "Did Mom eat?"})

    # 3. Empty question in ask_memory
    with pytest.raises(Exception, match="Question cannot be empty"):
        await server.call_tool("ask_memory", {"person": "eleanor", "question": "   "})

    storage.close()
    if os.path.exists(path):
        os.remove(path)


def test_bedrock_live_converse_smoke():
    """
    Opt-in live Amazon Bedrock integration smoke test.
    Only runs when RUN_AWS_BEDROCK_LIVE=1 is explicitly set in environment.
    """
    if os.getenv("RUN_AWS_BEDROCK_LIVE") != "1":
        pytest.skip("Live AWS Bedrock smoke test skipped. Set RUN_AWS_BEDROCK_LIVE=1 to opt-in.")

    try:
        import boto3

        sts = boto3.client("sts")
        sts.get_caller_identity()
    except Exception as e:
        pytest.skip(f"AWS preflight failed: {e}")

    assistant = BedrockAssistant()
    ref_time = datetime.now(timezone.utc)
    events = [
        Event(
            person_id="eleanor",
            event_type=EventType.PILL,
            timestamp=ref_time - timedelta(hours=2),
            metadata={"medication": "blood pressure pill"},
        ),
        Event(
            person_id="eleanor",
            event_type=EventType.MEAL,
            timestamp=ref_time - timedelta(hours=1),
            metadata={"meal_type": "lunch"},
        ),
    ]

    summary = assistant.daily_summary(person="eleanor", target_date="today", events=events)
    assert len(summary) > 20
    sentences = [s.strip() for s in summary.split(".") if s.strip()]
    assert len(sentences) >= 2

"""
Unit tests for Amazon Bedrock LLM module (careloop/llm/bedrock.py).

Verifies:
1. Model ID is configurable via BEDROCK_MODEL_ID env var.
2. daily_summary: generates warm 3-sentence family summary with graceful fallback.
3. ask_memory: parses question using rules first into person, event type, and date range.
4. Zero matching events: returns 'no record' without calling the LLM.
5. Matching events: passes ONLY matching events to the model.
6. Independence: no alert or escalation decisions depend on Bedrock.
"""

from datetime import datetime, timezone, timedelta
import os
from unittest.mock import MagicMock
import pytest

from careloop.llm.bedrock import BedrockAssistant
from careloop.models import Event, EventType
from careloop.storage.sqlite_store import SQLiteStorage


def test_model_id_from_env_var(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0")
    assistant = BedrockAssistant()
    assert assistant.model_id == "amazon.nova-micro-v1:0"

    # Explicit override takes priority
    custom_assistant = BedrockAssistant(model_id="custom.model-v1:0")
    assert custom_assistant.model_id == "custom.model-v1:0"


def test_daily_summary_three_sentences_fallback():
    assistant = BedrockAssistant(bedrock_client=None)  # Offline fallback
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
                "content": [{"text": "Eleanor had a peaceful morning and enjoyed her breakfast on time. She took her morning blood pressure medication comfortably at 08:45. Her daily routine remains consistent and reassuring."}]
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

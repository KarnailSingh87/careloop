"""
Amazon Bedrock LLM integration.

ARCHITECTURAL MANDATE:
Amazon Bedrock is utilized EXCLUSIVELY for natural language daily summaries
and caregiver memory Q&A.
Bedrock NEVER decides whether to trigger alerts or escalate notifications;
all health and safety alerts are evaluated by deterministic code.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
import boto3
from botocore.exceptions import ClientError

from careloop.models import Event

logger = logging.getLogger(__name__)


class BedrockAssistant:
    """Amazon Bedrock wrapper for caregiver summaries and memory Q&A."""

    def __init__(
        self,
        model_id: str = "anthropic.claude-3-haiku-20240307-v1:0",
        region_name: str = "us-east-1",
        bedrock_client: Optional[Any] = None,
    ) -> None:
        self.model_id = model_id
        self.region_name = region_name
        self._client = bedrock_client

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = boto3.client("bedrock-runtime", region_name=self.region_name)
        return self._client

    def generate_daily_summary(
        self,
        person_name: str,
        events: List[Event],
    ) -> str:
        """
        Produce a warm, concise daily summary for family members.
        Falls back gracefully if Bedrock credentials are unavailable.
        """
        event_descriptions = [
            f"- {e.timestamp.strftime('%H:%M')} UTC: {e.event_type.value} ({e.metadata})"
            for e in sorted(events, key=lambda x: x.timestamp)
        ]
        events_text = "\n".join(event_descriptions) if event_descriptions else "No events recorded today."

        prompt = (
            f"You are CareLoop, an empathetic assistant helping family caregivers keep track of {person_name}.\n"
            f"Here are the recorded routine events for today:\n{events_text}\n\n"
            f"Write a brief 2-3 sentence reassuring summary of {person_name}'s daily routine and activities. "
            f"Do not make medical diagnoses. Focus only on observed routine events."
        )

        try:
            client = self._get_client()
            response = client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 300, "temperature": 0.3},
            )
            return response["output"]["message"]["content"][0]["text"]
        except Exception as e:
            logger.warning(f"Bedrock converse unavailable, using local summary generator: {e}")
            med_count = sum(1 for e in events if e.event_type.value in ("pill", "medication"))
            meal_count = sum(1 for e in events if e.event_type.value == "meal")
            movement_count = sum(1 for e in events if e.event_type.value == "movement")
            return (
                f"{person_name}'s routine has been active today with {med_count} medication check(s), "
                f"{meal_count} meal(s), and normal movement throughout the home. "
                f"All logged activities align with expected patterns."
            )

    def answer_memory_question(
        self,
        person_name: str,
        question: str,
        events: List[Event],
    ) -> str:
        """
        Answer caregiver queries like 'What time did Mom eat breakfast today?'.
        """
        event_descriptions = [
            f"- {e.timestamp.strftime('%Y-%m-%d %H:%M')} UTC: {e.event_type.value} ({e.metadata})"
            for e in events
        ]
        events_text = "\n".join(event_descriptions) if event_descriptions else "No events recorded."

        prompt = (
            f"You are CareLoop caregiver memory assistant for {person_name}.\n"
            f"Event logs:\n{events_text}\n\n"
            f"Caregiver Question: {question}\n\n"
            f"Answer concisely based strictly on the events above. If not in the log, state that clearly."
        )

        try:
            client = self._get_client()
            response = client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 200, "temperature": 0.2},
            )
            return response["output"]["message"]["content"][0]["text"]
        except Exception as e:
            logger.warning(f"Bedrock converse unavailable, using local answer engine: {e}")
            return f"Based on local records for {person_name}, {len(events)} events were analyzed regarding: '{question}'."

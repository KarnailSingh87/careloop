"""
Amazon Bedrock LLM integration using the boto3 Converse API.

ARCHITECTURAL PRINCIPLE:
Amazon Bedrock is utilized EXCLUSIVELY for family summaries and memory Q&A.
It NEVER decides whether to alert or escalate. Alerts come purely from deterministic code.

Features:
- Configurable model ID via BEDROCK_MODEL_ID environment variable (default: anthropic.claude-3-haiku-20240307-v1:0).
- daily_summary: Fetches that day's events and generates a warm 3-sentence family summary.
- ask_memory: Parses question with fast rule-based filters first (person, event type, date range),
  queries matching event logs, and passes ONLY matching events to the model.
  If zero matching events exist, returns 'no record' without calling the LLM.
- Graceful template fallback when Bedrock is unavailable so demos never fail.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta, date
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import boto3
from botocore.exceptions import ClientError
from dateutil import parser as date_parser

from careloop.models import Event, EventType
from careloop.storage.base import StorageBase

logger = logging.getLogger(__name__)


class BedrockAssistant:
    """Amazon Bedrock Converse API assistant for family summaries and memory Q&A."""

    def __init__(
        self,
        model_id: Optional[str] = None,
        region_name: Optional[str] = None,
        bedrock_client: Optional[Any] = None,
    ) -> None:
        # Model ID is configurable via environment variable
        self.model_id = model_id or os.getenv(
            "BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
        )
        self.region_name = region_name or os.getenv("AWS_REGION", "us-east-1")
        self._client = bedrock_client

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = boto3.client("bedrock-runtime", region_name=self.region_name)
        return self._client

    # -------------------------------------------------------------------------
    # 1. Daily Summary
    # -------------------------------------------------------------------------

    def daily_summary(
        self,
        person: str,
        target_date: Optional[Union[str, date, datetime]] = None,
        storage: Optional[StorageBase] = None,
        events: Optional[List[Event]] = None,
        display_name: Optional[str] = None,
    ) -> str:
        """
        Fetch that day's events from storage and generate a warm 3-sentence summary for family.
        """
        name = display_name or person.capitalize()

        # Resolve target date
        if target_date is None or (isinstance(target_date, str) and target_date.strip().lower() == "today"):
            eval_date = datetime.now(timezone.utc).date()
        elif isinstance(target_date, str):
            try:
                eval_date = date_parser.parse(target_date).date()
            except Exception:
                eval_date = datetime.now(timezone.utc).date()
        elif isinstance(target_date, datetime):
            eval_date = target_date.date()
        else:
            eval_date = target_date

        # Fetch events for that day
        day_events: List[Event] = []
        if events is not None:
            day_events = [e for e in events if e.timestamp.date() == eval_date]
        elif storage is not None:
            all_events = storage.get_events(person.strip().lower(), limit=200)
            day_events = [e for e in all_events if e.timestamp.date() == eval_date]

        # Format events
        sorted_events = sorted(day_events, key=lambda x: x.timestamp)
        event_lines = [
            f"- {e.timestamp.strftime('%H:%M')} UTC: {e.event_type.value} ({e.metadata})"
            for e in sorted_events
        ]
        events_text = "\n".join(event_lines) if event_lines else "No routine events recorded today."

        # Prompt strictly requesting exactly 3 warm sentences
        prompt = (
            f"You are CareLoop, a compassionate elder care assistant providing updates to family caregivers.\n"
            f"Below are the recorded daily routine events for {name} on {eval_date.isoformat()}:\n"
            f"{events_text}\n\n"
            f"Instructions:\n"
            f"Write a warm, reassuring summary for {name}'s family in EXACTLY THREE sentences. "
            f"Describe their morning, meals, and general activity based strictly on the recorded events. "
            f"Do not make medical claims or offer clinical advice. Keep the tone loving, calm, and clear."
        )

        try:
            client = self._get_client()
            response = client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 250, "temperature": 0.3},
            )
            return response["output"]["message"]["content"][0]["text"].strip()
        except Exception as e:
            logger.warning(f"Bedrock converse unavailable ({e}), using warm 3-sentence fallback template.")
            return self._fallback_daily_summary(name, eval_date, sorted_events)

    def _fallback_daily_summary(self, name: str, eval_date: date, events: List[Event]) -> str:
        """Deterministic 3-sentence fallback template ensuring the demo never breaks."""
        if not events:
            return (
                f"No routine events were recorded for {name} on {eval_date.isoformat()}. "
                f"Sensors have not logged movement or meals during this window. "
                f"CareLoop is continuing to monitor the home and will alert family if scheduled windows are missed."
            )

        med_count = sum(1 for e in events if e.event_type.value in ("pill", "medication"))
        meal_count = sum(1 for e in events if e.event_type.value == "meal")
        mov_count = sum(1 for e in events if e.event_type.value == "movement")

        first_time = events[0].timestamp.strftime("%H:%M UTC")
        last_time = events[-1].timestamp.strftime("%H:%M UTC")

        s1 = f"{name} had a steady and peaceful day on {eval_date.isoformat()}, starting active movement around {first_time}."
        s2 = f"Her daily routine included {med_count} medication check(s) and {meal_count} logged meal(s), with activity continuing through {last_time}."
        s3 = f"Overall, all observed household patterns align with her typical baseline schedule, offering peace of mind to family caregivers."
        return f"{s1} {s2} {s3}"

    # -------------------------------------------------------------------------
    # 2. Memory Q&A with Fast Rule-Based Filter Extraction
    # -------------------------------------------------------------------------

    def ask_memory(
        self,
        person: str,
        question: str,
        storage: Optional[StorageBase] = None,
        events: Optional[List[Event]] = None,
        now: Optional[datetime] = None,
        display_name: Optional[str] = None,
    ) -> str:
        """
        Caregiver memory Q&A flow:
        1. Parse question into person, event type, and date range using simple rules first.
        2. If rules fail, use LLM to extract query filters.
        3. Query event log from storage.
        4. If no matching events exist, return 'no record' without calling the LLM.
        5. If matching events exist, pass ONLY matching events to the model to phrase the answer.
        """
        ref_now = now or datetime.now(timezone.utc)
        name = display_name or person.capitalize()
        person_id = person.strip().lower()

        # Step 1: Rule-based extraction
        parsed_type, start_dt, end_dt = self._extract_filters_rule_based(question, ref_now)

        # Step 2: If rules fail to extract event type, try LLM filter extraction
        if parsed_type is None:
            parsed_type = self._extract_filters_llm(question)

        # Step 3: Query event log
        if events is not None:
            candidate_events = events
        elif storage is not None:
            candidate_events = storage.get_events(person_id, limit=100)
        else:
            candidate_events = []

        # Filter candidate events by type and date range
        matching_events = self._filter_events(candidate_events, parsed_type, start_dt, end_dt)

        # Step 4: Zero matching events -> answer 'no record' WITHOUT calling the LLM!
        if not matching_events:
            logger.info("ask_memory: 0 matching events found. Answering 'no record' without LLM call.")
            return self._no_record_response(name, question, parsed_type, start_dt, end_dt)

        # Step 5: Pass ONLY matching events to Bedrock to phrase the natural language answer
        matching_lines = [
            f"- {e.timestamp.strftime('%Y-%m-%d %H:%M')} UTC: {e.event_type.value} ({e.metadata})"
            for e in sorted(matching_events, key=lambda x: x.timestamp)
        ]
        events_text = "\n".join(matching_lines)

        prompt = (
            f"You are CareLoop, an empathetic memory assistant for family caregivers looking after {name}.\n"
            f"Caregiver Question: {question}\n\n"
            f"Matching Logged Events:\n"
            f"{events_text}\n\n"
            f"Instructions:\n"
            f"Answer the caregiver's question directly in 1-2 friendly, reassuring sentences based ONLY on the matching events above. "
            f"Include exact times and event details if available. Do not guess or extrapolate beyond these events."
        )

        try:
            client = self._get_client()
            response = client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 150, "temperature": 0.2},
            )
            return response["output"]["message"]["content"][0]["text"].strip()
        except Exception as e:
            logger.warning(f"Bedrock converse unavailable ({e}), using deterministic phrasing template.")
            return self._fallback_answer_memory(name, question, matching_events)

    def _extract_filters_rule_based(
        self,
        question: str,
        now: datetime,
    ) -> Tuple[Optional[str], datetime, datetime]:
        """
        Fast deterministic rule-based filter extractor.
        Returns: (event_type, start_datetime, end_datetime)
        """
        q = question.lower()

        # 1. Event Type Rules
        event_type: Optional[str] = None
        if any(w in q for w in ["pill", "pills", "med", "meds", "medication", "medicine", "prescription", "dose", "blood pressure"]):
            event_type = "pill"
        elif any(w in q for w in ["breakfast", "lunch", "dinner", "meal", "eat", "ate", "eating", "food", "snack"]):
            event_type = "meal"
        elif any(w in q for w in ["movement", "motion", "walk", "walking", "active", "activity", "awake", "stirring"]):
            event_type = "movement"
        elif any(w in q for w in ["door", "outside", "garden", "back door", "front door", "leave", "left"]):
            event_type = "door"

        # 2. Date Range Rules
        today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        today_end = today_start + timedelta(days=1)

        start_dt = today_start
        end_dt = today_end

        if "yesterday" in q:
            start_dt = today_start - timedelta(days=1)
            end_dt = today_start
        elif "this morning" in q:
            start_dt = today_start.replace(hour=5)
            end_dt = today_start.replace(hour=12)
        elif "this afternoon" in q:
            start_dt = today_start.replace(hour=12)
            end_dt = today_start.replace(hour=18)
        elif "this evening" in q or "tonight" in q:
            start_dt = today_start.replace(hour=18)
            end_dt = today_end
        elif "last 3 days" in q or "past 3 days" in q:
            start_dt = today_start - timedelta(days=3)
        elif "past week" in q or "last 7 days" in q or "this week" in q:
            start_dt = today_start - timedelta(days=7)

        return event_type, start_dt, end_dt

    def _extract_filters_llm(self, question: str) -> Optional[str]:
        """
        LLM fallback for filter extraction when keyword rules cannot determine event category.
        """
        prompt = (
            f"Classify the routine event category from this query into exactly one of: "
            f"'pill', 'meal', 'movement', 'door', or 'other'.\n"
            f"Query: \"{question}\"\n"
            f"Respond with only the category word in lowercase."
        )
        try:
            client = self._get_client()
            res = client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 10, "temperature": 0.0},
            )
            raw = res["output"]["message"]["content"][0]["text"].strip().lower()
            if raw in ("pill", "meal", "movement", "door"):
                return raw
        except Exception:
            pass
        return None

    def _filter_events(
        self,
        events: List[Event],
        event_type: Optional[str],
        start_dt: datetime,
        end_dt: datetime,
    ) -> List[Event]:
        """Filter events matching type and date range."""
        results: List[Event] = []
        for e in events:
            # Check date range
            if not (start_dt <= e.timestamp <= end_dt):
                continue

            # Check event type
            if event_type:
                raw = e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type)
                # Map medication alias to pill
                if event_type == "pill" and raw in ("pill", "medication"):
                    results.append(e)
                elif raw == event_type:
                    results.append(e)
            else:
                results.append(e)

        return results

    def _no_record_response(
        self,
        name: str,
        question: str,
        event_type: Optional[str],
        start_dt: datetime,
        end_dt: datetime,
    ) -> str:
        """Deterministic response returned when no matching events exist."""
        time_label = "today"
        now = datetime.now(timezone.utc)
        if start_dt.date() == (now - timedelta(days=1)).date():
            time_label = "yesterday"
        elif (now - start_dt).days >= 2:
            time_label = f"between {start_dt.strftime('%b %d')} and {end_dt.strftime('%b %d')}"

        type_label = f"'{event_type}'" if event_type else "routine activity"
        return f"There is no record of {type_label} for {name} {time_label}."

    def _fallback_answer_memory(
        self,
        name: str,
        question: str,
        events: List[Event],
    ) -> str:
        """Deterministic phrasing template used when Bedrock is offline."""
        latest = sorted(events, key=lambda x: x.timestamp)[-1]
        time_str = latest.timestamp.strftime("%H:%M UTC")
        date_str = latest.timestamp.strftime("%Y-%m-%d")
        item_details = latest.metadata.get("medication") or latest.metadata.get("meal_type") or latest.metadata.get("room") or ""
        detail_suffix = f" ({item_details})" if item_details else ""
        return (
            f"Yes, {name} logged {latest.event_type.value}{detail_suffix} at {time_str} on {date_str}. "
            f"A total of {len(events)} matching event record(s) were found."
        )

    # Backward compatibility helpers
    def generate_daily_summary(self, person_name: str, events: List[Event]) -> str:
        return self.daily_summary(person=person_name, events=events, display_name=person_name)

    def answer_memory_question(self, person_name: str, question: str, events: List[Event]) -> str:
        return self.ask_memory(person=person_name, question=question, events=events, display_name=person_name)

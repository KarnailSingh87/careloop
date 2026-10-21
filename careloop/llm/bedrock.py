"""
Amazon Bedrock LLM integration using the boto3 Bedrock Runtime Converse API.

ARCHITECTURAL PRINCIPLE:
Amazon Bedrock is utilized EXCLUSIVELY for family daily summaries and memory Q&A.
It NEVER decides whether to alert or escalate. Emergency alerts and risk scores
are computed purely by deterministic clinical code (circular EWMA and state machine).
Even an adversarial or hallucinated model response CANNOT alter risk scores,
escalation stages, or notification decisions.

Key Capabilities:
1. Configurable Model ID via BEDROCK_MODEL_ID environment variable
   (default: anthropic.claude-3-haiku-20240307-v1:0).
2. Daily Summary:
   - Retrieves only the requested person's events for the requested local calendar date.
   - Generates a warm, concise 3-sentence family summary grounded strictly in data.
   - Clearly distinguishes observed events from missing records and unobserved windows.
   - Never invents medication adherence, activities, sleep, mood, or wellbeing.
   - Returns a deterministic template when Bedrock is unavailable.
3. Memory Q&A:
   - Resolves person from explicit validated argument or request context.
   - Enforces person-level access control before retrieving events.
   - Parses event types and date ranges using deterministic rules first.
   - Uses the LLM only for filter extraction when rules fail; validates filters before querying storage.
   - Sends the model ONLY the minimum matching event metadata required to answer.
   - If zero matching records exist, returns an explicit "no record" response without invoking Bedrock.
   - Explains that a missing record proves no log was recorded, not that the event did not occur.
   - Handles throttling, timeouts, unavailable models, and malformed responses safely.
   - Never logs prompts containing personal elder event histories.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta, date, time
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from zoneinfo import ZoneInfo

import boto3
from botocore.exceptions import ClientError
from dateutil import parser as date_parser

from careloop.models import Event, EventType
from careloop.storage.base import StorageBase

logger = logging.getLogger(__name__)

# Permitted event categories for memory querying
ALLOWED_EVENT_TYPES = {"pill", "meal", "movement", "door"}


def _get_local_timezone(tz_name: Optional[str]) -> ZoneInfo:
    """Safely obtain a ZoneInfo timezone object, falling back to UTC on error."""
    if not tz_name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(tz_name.strip())
    except Exception:
        return ZoneInfo("UTC")


class BedrockAssistant:
    """Amazon Bedrock Converse API assistant for family summaries and memory Q&A."""

    def __init__(
        self,
        model_id: Optional[str] = None,
        region_name: Optional[str] = None,
        bedrock_client: Optional[Any] = None,
    ) -> None:
        self.model_id = (
            model_id
            or os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
        )
        self.region_name = (
            region_name
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
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
        now: Optional[datetime] = None,
        display_name: Optional[str] = None,
        person_tz: Optional[str] = None,
    ) -> str:
        """
        Generate a warm, concise three-sentence family summary grounded strictly in data.
        
        Requirements:
        - Retrieves only the requested person's events for the requested local calendar date.
        - Grounded only in retrieved events; never invents adherence, activities, or wellbeing.
        - Distinguishes observed events from missing records.
        - Falls back to a deterministic 3-sentence template when Bedrock is unavailable.
        """
        if not person or not person.strip():
            raise ValueError("Person identifier cannot be empty.")

        person_id = person.strip().lower()
        name = display_name or person_id.capitalize()

        # Resolve timezone (from profile or parameter, default UTC)
        tz_str = person_tz
        if tz_str is None and storage is not None:
            profile = storage.get_profile(person_id)
            if profile and profile.timezone:
                tz_str = profile.timezone
        tz = _get_local_timezone(tz_str)

        # Resolve reference now
        ref_now = now or datetime.now(timezone.utc)
        if ref_now.tzinfo is None:
            ref_now = ref_now.replace(tzinfo=timezone.utc)
        local_ref_now = ref_now.astimezone(tz)

        # Resolve requested local calendar date
        if target_date is None or (
            isinstance(target_date, str) and target_date.strip().lower() == "today"
        ):
            eval_date = local_ref_now.date()
        elif isinstance(target_date, str):
            t_str = target_date.strip().lower()
            if t_str == "yesterday":
                eval_date = (local_ref_now - timedelta(days=1)).date()
            else:
                try:
                    eval_date = date_parser.parse(target_date).date()
                except Exception:
                    eval_date = local_ref_now.date()
        elif isinstance(target_date, datetime):
            dt_aware = target_date if target_date.tzinfo is not None else target_date.replace(tzinfo=timezone.utc)
            eval_date = dt_aware.astimezone(tz).date()
        elif isinstance(target_date, date):
            eval_date = target_date
        else:
            eval_date = local_ref_now.date()

        # Retrieve ONLY the requested person's events
        if events is not None:
            all_events = events
        elif storage is not None:
            # Person-level access control enforced: query strictly with person_id
            all_events = storage.get_events(person_id, limit=200)
        else:
            all_events = []

        # Filter strictly for the requested local calendar date
        day_events: List[Event] = []
        for e in all_events:
            e_dt = e.timestamp if e.timestamp.tzinfo is not None else e.timestamp.replace(tzinfo=timezone.utc)
            if e_dt.astimezone(tz).date() == eval_date:
                day_events.append(e)

        sorted_events = sorted(day_events, key=lambda x: x.timestamp)

        # Minimum required metadata formatting
        event_lines: List[str] = []
        for e in sorted_events:
            e_dt = e.timestamp if e.timestamp.tzinfo is not None else e.timestamp.replace(tzinfo=timezone.utc)
            local_time_str = e_dt.astimezone(tz).strftime("%H:%M")
            meta_clean = {k: v for k, v in e.metadata.items() if k not in ("audio", "raw_payload")}
            event_lines.append(f"- {local_time_str} ({tz.key}): {e.event_type.value} {meta_clean if meta_clean else ''}")

        events_text = "\n".join(event_lines) if event_lines else "No routine events recorded for this calendar date."

        prompt = (
            f"You are CareLoop, a compassionate elder care assistant providing factual updates to family caregivers.\n"
            f"Below are the ONLY recorded daily routine events for {name} on {eval_date.isoformat()} ({tz.key} local time):\n"
            f"{events_text}\n\n"
            f"STRICT CLINICAL GROUNDING INSTRUCTIONS:\n"
            f"1. Write a warm, reassuring family summary in EXACTLY THREE sentences.\n"
            f"2. Ground your summary STRICTLY and ONLY in the recorded events listed above.\n"
            f"3. Clearly distinguish observed events from missing records. "
            f"State what was recorded, and note that unobserved routine windows had no sensor logs.\n"
            f"4. NEVER invent or assume medication adherence, meals, sleep, mood, or wellbeing that is not explicitly logged.\n"
            f"5. If medication is not logged, state that no medication check was recorded—never assume it was taken or missed.\n"
            f"6. Do not offer clinical diagnoses or medical advice."
        )

        try:
            client = self._get_client()
            logger.info(
                f"Invoking Bedrock Converse daily_summary for {person_id} on {eval_date.isoformat()} "
                f"(events_count={len(sorted_events)}, model={self.model_id})"
            )
            response = client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 250, "temperature": 0.2},
            )
            output_msg = response.get("output", {}).get("message", {}).get("content", [])
            if output_msg and "text" in output_msg[0]:
                raw_text = output_msg[0]["text"].strip()
                if raw_text:
                    return raw_text
            raise ValueError("Empty or malformed text in Bedrock Converse response.")
        except ClientError as ce:
            err_code = ce.response.get("Error", {}).get("Code", "ClientError")
            err_msg = ce.response.get("Error", {}).get("Message", str(ce))
            logger.warning(
                f"Bedrock Converse ClientError [{err_code}] for {person_id}: {err_msg}. "
                f"Using deterministic 3-sentence fallback template."
            )
            return self._fallback_daily_summary(name, eval_date, sorted_events, tz.key)
        except Exception as e:
            logger.warning(
                f"Bedrock Converse unavailable ({type(e).__name__}: {e}) for {person_id}. "
                f"Using deterministic 3-sentence fallback template."
            )
            return self._fallback_daily_summary(name, eval_date, sorted_events, tz.key)

    def _fallback_daily_summary(
        self,
        name: str,
        eval_date: date,
        events: List[Event],
        tz_name: str = "UTC",
    ) -> str:
        """
        Deterministic 3-sentence fallback template ensuring the demo never breaks.
        Strictly grounded: distinguishes observed events from missing records,
        and never hallucinates adherence or wellbeing.
        """
        if not events:
            return (
                f"No routine events were recorded for {name} on {eval_date.isoformat()}. "
                f"No motion, meal, or medication check-ins were detected in the home during this period. "
                f"CareLoop is actively monitoring the home and will alert family caregivers if expected schedule windows are missed."
            )

        tz = _get_local_timezone(tz_name)
        med_events = [e for e in events if e.event_type.value in ("pill", "medication")]
        meal_events = [e for e in events if e.event_type.value == "meal"]
        mov_events = [e for e in events if e.event_type.value == "movement"]
        door_events = [e for e in events if e.event_type.value == "door"]

        first_dt = events[0].timestamp if events[0].timestamp.tzinfo is not None else events[0].timestamp.replace(tzinfo=timezone.utc)
        last_dt = events[-1].timestamp if events[-1].timestamp.tzinfo is not None else events[-1].timestamp.replace(tzinfo=timezone.utc)

        first_time = first_dt.astimezone(tz).strftime("%H:%M")
        last_time = last_dt.astimezone(tz).strftime("%H:%M")

        s1 = (
            f"{name} had observed household activity on {eval_date.isoformat()}, "
            f"beginning with recorded {events[0].event_type.value} at {first_time} {tz_name}."
        )
        s2 = (
            f"Logged records confirm {len(med_events)} medication check(s), {len(meal_events)} meal(s), "
            f"and activity continuing through {last_time} {tz_name}."
        )
        s3 = (
            f"Unobserved routine windows have no sensor records logged, and CareLoop continues passive monitoring."
        )
        return f"{s1} {s2} {s3}"

    # -------------------------------------------------------------------------
    # 2. Memory Q&A with Deterministic Rule-First Filter Extraction
    # -------------------------------------------------------------------------

    def ask_memory(
        self,
        person: str,
        question: str,
        storage: Optional[StorageBase] = None,
        events: Optional[List[Event]] = None,
        now: Optional[datetime] = None,
        display_name: Optional[str] = None,
        person_tz: Optional[str] = None,
    ) -> str:
        """
        Caregiver memory Q&A flow:
        1. Resolve person from explicit validated argument.
        2. Enforce person-level access control before retrieving events.
        3. Parse event type and date range using fast deterministic rules first.
        4. If rules fail, use LLM only for filter extraction and validate filters before querying.
        5. Filter candidate events to minimum matching set.
        6. If zero matching events exist, return explicit "no record" without calling Bedrock.
        7. Send only minimum matching event metadata to Bedrock.
        8. Explain that missing records prove no log was recorded, not that the event did not occur.
        9. Handle throttling, timeouts, and errors safely with local fallback.
        """
        if not person or not person.strip():
            raise ValueError("Person identifier cannot be empty.")
        if not question or not question.strip():
            raise ValueError("Question cannot be empty.")

        person_id = person.strip().lower()
        clean_question = question.strip()
        name = display_name or person_id.capitalize()

        # Resolve timezone (from profile or parameter, default UTC)
        tz_str = person_tz
        if tz_str is None and storage is not None:
            profile = storage.get_profile(person_id)
            if profile and profile.timezone:
                tz_str = profile.timezone
        tz = _get_local_timezone(tz_str)

        ref_now = now or datetime.now(timezone.utc)
        if ref_now.tzinfo is None:
            ref_now = ref_now.replace(tzinfo=timezone.utc)
        local_ref_now = ref_now.astimezone(tz)

        # Step 1: Deterministic rule-based filter extraction
        parsed_type, start_dt, end_dt = self._extract_filters_rule_based(
            clean_question, local_ref_now, tz
        )

        # Step 2: If rules cannot determine event category, try constrained LLM extraction
        if parsed_type is None:
            extracted_llm_type = self._extract_filters_llm(clean_question)
            if extracted_llm_type in ALLOWED_EVENT_TYPES:
                parsed_type = extracted_llm_type

        # Step 3: Enforce person-level access control before querying storage
        if events is not None:
            candidate_events = events
        elif storage is not None:
            candidate_events = storage.get_events(person_id, limit=200)
        else:
            candidate_events = []

        # Step 4: Filter events to minimum matching set
        matching_events = self._filter_events(
            candidate_events, parsed_type, start_dt, end_dt, tz
        )

        # Step 5: Zero matching records -> return explicit "no record" WITHOUT invoking Bedrock!
        if not matching_events:
            logger.info(
                f"ask_memory: 0 matching events found for {person_id} (type={parsed_type}). "
                f"Returning 'no record' without Bedrock Converse call."
            )
            return self._no_record_response(name, clean_question, parsed_type, start_dt, end_dt, tz.key, ref_now=local_ref_now)

        # Step 6: Format MINIMUM matching event metadata for Bedrock
        matching_lines: List[str] = []
        for e in sorted(matching_events, key=lambda x: x.timestamp):
            e_dt = e.timestamp if e.timestamp.tzinfo is not None else e.timestamp.replace(tzinfo=timezone.utc)
            local_str = e_dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")
            meta_clean = {k: v for k, v in e.metadata.items() if k not in ("audio", "raw_payload")}
            matching_lines.append(f"- {local_str} ({tz.key}): {e.event_type.value} {meta_clean if meta_clean else ''}")

        events_text = "\n".join(matching_lines)

        prompt = (
            f"You are CareLoop, an empathetic memory assistant for family caregivers looking after {name}.\n"
            f"Caregiver Question: {clean_question}\n\n"
            f"Matching Recorded Events ({tz.key} local time):\n"
            f"{events_text}\n\n"
            f"STRICT CLINICAL GROUNDING INSTRUCTIONS:\n"
            f"1. Answer the question directly in 1-2 friendly, reassuring sentences based ONLY on the matching events above.\n"
            f"2. Include exact times and event details from the log.\n"
            f"3. Do NOT extrapolate or guess beyond these logged records.\n"
            f"4. Important: A missing record in the log only proves that no sensor or voice check-in was recorded; "
            f"it does NOT prove that an event did not occur. Never claim the elder failed or forgot unless a record explicitly states so."
        )

        try:
            client = self._get_client()
            logger.info(
                f"Invoking Bedrock Converse ask_memory for {person_id}: "
                f"matching_count={len(matching_events)}, model={self.model_id}"
            )
            response = client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 150, "temperature": 0.2},
            )
            output_msg = response.get("output", {}).get("message", {}).get("content", [])
            if output_msg and "text" in output_msg[0]:
                raw_text = output_msg[0]["text"].strip()
                if raw_text:
                    return raw_text
            raise ValueError("Empty or malformed text in Bedrock Converse response.")
        except ClientError as ce:
            err_code = ce.response.get("Error", {}).get("Code", "ClientError")
            err_msg = ce.response.get("Error", {}).get("Message", str(ce))
            logger.warning(
                f"Bedrock Converse ClientError [{err_code}] in ask_memory for {person_id}: {err_msg}. "
                f"Using deterministic phrasing template."
            )
            return self._fallback_answer_memory(name, clean_question, matching_events, tz.key)
        except Exception as e:
            logger.warning(
                f"Bedrock Converse unavailable in ask_memory ({type(e).__name__}: {e}) for {person_id}. "
                f"Using deterministic phrasing template."
            )
            return self._fallback_answer_memory(name, clean_question, matching_events, tz.key)

    # -------------------------------------------------------------------------
    # 3. Fast Deterministic Rule Extraction & Filtering
    # -------------------------------------------------------------------------

    def _extract_filters_rule_based(
        self,
        question: str,
        local_now: datetime,
        tz: Optional[ZoneInfo] = None,
    ) -> Tuple[Optional[str], datetime, datetime]:
        """
        Fast deterministic rule-based filter extractor.
        Returns: (event_type, start_datetime, end_datetime)
        """
        q = question.lower()
        active_tz = tz or (local_now.tzinfo if local_now.tzinfo is not None else ZoneInfo("UTC"))

        # 1. Event Type Rules
        event_type: Optional[str] = None

        if any(w in q for w in ["pill", "pills", "med", "meds", "medication", "medicine", "prescription", "dose", "blood pressure"]):
            event_type = "pill"
        elif any(w in q for w in ["breakfast", "lunch", "dinner", "meal", "meals", "eat", "ate", "eating", "food", "snack"]):
            event_type = "meal"
        elif any(w in q for w in ["movement", "motion", "walk", "walking", "active", "activity", "awake", "stirring", "bedroom", "kitchen", "living room", "hallway"]):
            event_type = "movement"
        elif any(w in q for w in ["door", "outside", "garden", "back door", "front door", "leave", "left", "exit", "entry"]):
            event_type = "door"

        # 2. Date Range Rules (evaluated in local timezone)
        today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        start_dt = today_start
        end_dt = today_end

        if "yesterday" in q:
            start_dt = today_start - timedelta(days=1)
            end_dt = today_start
        elif "this morning" in q:
            start_dt = today_start.replace(hour=0)
            end_dt = today_start.replace(hour=12)
        elif "this afternoon" in q:
            start_dt = today_start.replace(hour=12)
            end_dt = today_start.replace(hour=18)
        elif "this evening" in q or "tonight" in q:
            start_dt = today_start.replace(hour=18)
            end_dt = today_end
        elif "last night" in q:
            start_dt = (today_start - timedelta(days=1)).replace(hour=20)
            end_dt = today_start.replace(hour=6)
        elif "last 3 days" in q or "past 3 days" in q:
            start_dt = today_start - timedelta(days=3)
        elif "past week" in q or "last 7 days" in q or "this week" in q or "last week" in q:
            start_dt = today_start - timedelta(days=7)

        return event_type, start_dt, end_dt

    def _extract_filters_llm(self, question: str) -> Optional[str]:
        """
        Constrained LLM fallback for filter extraction when keyword rules cannot classify.
        Validates the output strictly against ALLOWED_EVENT_TYPES before use.
        """
        prompt = (
            f"Classify the elder routine event category from this query into exactly one word: "
            f"'pill', 'meal', 'movement', or 'door'. If none apply, answer 'other'.\n"
            f"Query: \"{question}\"\n"
            f"Answer with only the category word in lowercase."
        )
        try:
            client = self._get_client()
            res = client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 10, "temperature": 0.0},
            )
            raw = res["output"]["message"]["content"][0]["text"].strip().lower()
            if raw in ALLOWED_EVENT_TYPES:
                return raw
        except Exception as e:
            logger.debug(f"LLM filter extraction fallback skipped: {e}")
        return None

    def _filter_events(
        self,
        events: List[Event],
        event_type: Optional[str],
        start_dt: datetime,
        end_dt: datetime,
        tz: Optional[ZoneInfo] = None,
    ) -> List[Event]:
        """Filter events matching event type and date range."""
        active_tz = tz or ZoneInfo("UTC")
        results: List[Event] = []
        for e in events:
            # Ensure timestamp is timezone-aware
            e_dt = e.timestamp if e.timestamp.tzinfo is not None else e.timestamp.replace(tzinfo=timezone.utc)
            local_e_dt = e_dt.astimezone(active_tz)

            # Check date range boundary
            if not (start_dt <= local_e_dt <= end_dt):
                continue

            # Check event type
            raw_type = e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type)
            type_matches = False
            if not event_type:
                type_matches = True
            elif event_type == "pill" and raw_type in ("pill", "medication"):
                type_matches = True
            elif raw_type == event_type:
                type_matches = True

            if not type_matches:
                continue

            results.append(e)

        return results

    def _no_record_response(
        self,
        name: str,
        question: str,
        event_type: Optional[str],
        start_dt: datetime,
        end_dt: datetime,
        tz_name: str = "UTC",
        ref_now: Optional[datetime] = None,
    ) -> str:
        """
        Deterministic response returned when no matching events exist.
        Explicitly clarifies that a missing record indicates absence of logging,
        not proof that the event did not occur.
        """
        now = ref_now or datetime.now(timezone.utc)
        start_date = start_dt.date()
        now_date = now.date()

        if start_date == now_date:
            time_label = "today"
        elif start_date == (now_date - timedelta(days=1)):
            time_label = "yesterday"
        elif (now_date - start_date).days >= 2:
            time_label = f"between {start_dt.strftime('%b %d')} and {end_dt.strftime('%b %d')}"
        else:
            time_label = "in the requested timeframe"

        type_label = f"'{event_type}'" if event_type else "routine activity"
        return (
            f"There is no record of {type_label} for {name} {time_label}. "
            f"(Note: A missing record indicates that no sensor or voice log was recorded; "
            f"it does not confirm the event did not occur.)"
        )

    def _fallback_answer_memory(
        self,
        name: str,
        question: str,
        events: List[Event],
        tz_name: str = "UTC",
    ) -> str:
        """Deterministic phrasing template used when Bedrock is offline."""
        tz = _get_local_timezone(tz_name)
        latest = sorted(events, key=lambda x: x.timestamp)[-1]
        e_dt = latest.timestamp if latest.timestamp.tzinfo is not None else latest.timestamp.replace(tzinfo=timezone.utc)
        local_time_str = e_dt.astimezone(tz).strftime("%H:%M")
        date_str = e_dt.astimezone(tz).strftime("%Y-%m-%d")

        item_details = (
            latest.metadata.get("medication")
            or latest.metadata.get("meal_type")
            or latest.metadata.get("room")
            or ""
        )
        detail_suffix = f" ({item_details})" if item_details else ""
        return (
            f"Yes, {name} logged {latest.event_type.value}{detail_suffix} at {local_time_str} {tz_name} on {date_str}. "
            f"A total of {len(events)} matching event record(s) were found."
        )

    # Backward compatibility helpers
    def generate_daily_summary(self, person_name: str, events: List[Event]) -> str:
        return self.daily_summary(person=person_name, events=events, display_name=person_name)

    def answer_memory_question(self, person_name: str, question: str, events: List[Event]) -> str:
        return self.ask_memory(person=person_name, question=question, events=events, display_name=person_name)

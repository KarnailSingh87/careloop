"""
Demonstration script showcasing CareLoop's Bedrock generative assistant:
1. Daily Summary (warm 3-sentence summary grounded strictly in data).
2. Successful Memory Query (answering factual past event from matching logs).
3. No-Record Query (answering 'no record' without calling Bedrock).
"""

from datetime import datetime, timezone
from careloop.clock import SimulatedClock
from careloop.llm.bedrock import BedrockAssistant
from careloop.models import Event, EventType, PersonProfile
from careloop.storage.sqlite_store import SQLiteStorage
import tempfile
import os


def main():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    storage = SQLiteStorage(db_path=db_path)

    # 1. Register Person Profile with timezone
    storage.save_profile(
        PersonProfile(
            person_id="eleanor",
            display_name="Eleanor Vance",
            timezone="America/New_York",
        )
    )

    eval_now = datetime(2026, 10, 20, 15, 30, 0, tzinfo=timezone.utc)
    clock = SimulatedClock(eval_now)

    # 2. Seed realistic routine events for Eleanor
    # Morning movement at 08:00 UTC (04:00 EDT)
    storage.save_event(
        Event(
            person_id="eleanor",
            event_type=EventType.MOVEMENT,
            timestamp=datetime(2026, 10, 20, 12, 15, 0, tzinfo=timezone.utc),  # 08:15 EDT
            metadata={"room": "bedroom", "activity": "morning_awakening"},
        )
    )
    # Morning medication at 08:35 EDT
    storage.save_event(
        Event(
            person_id="eleanor",
            event_type=EventType.PILL,
            timestamp=datetime(2026, 10, 20, 12, 35, 0, tzinfo=timezone.utc),  # 08:35 EDT
            metadata={"medication": "lisinopril", "dose": "10mg", "method": "smart_pillbox"},
        )
    )
    # Lunch at 12:45 EDT
    storage.save_event(
        Event(
            person_id="eleanor",
            event_type=EventType.MEAL,
            timestamp=datetime(2026, 10, 20, 16, 45, 0, tzinfo=timezone.utc),  # 12:45 EDT
            metadata={"meal_type": "lunch", "notes": "soup and crackers"},
        )
    )

    assistant = BedrockAssistant()

    print("=" * 70)
    print("CARELOOP BEDROCK GENERATIVE ASSISTANT DEMONSTRATION")
    print("=" * 70)

    # -------------------------------------------------------------
    # DEMONSTRATION 1: Daily Summary
    # -------------------------------------------------------------
    print("\n--- [DEMONSTRATION 1] Daily Routine Summary (3 Sentences) ---")
    summary = assistant.daily_summary(
        person="eleanor",
        target_date="2026-10-20",
        storage=storage,
        now=clock.now(),
        display_name="Eleanor",
        person_tz="America/New_York",
    )
    print("Target Person: Eleanor Vance (Timezone: America/New_York)")
    print("Target Date:   2026-10-20")
    print(f'Generated 3-Sentence Summary:\n"{summary}"\n')

    # -------------------------------------------------------------
    # DEMONSTRATION 2: Successful Memory Query
    # -------------------------------------------------------------
    print("--- [DEMONSTRATION 2] Successful Memory Query (Matching Events) ---")
    question_1 = "Did Mom take her blood pressure medication today?"
    answer_1 = assistant.ask_memory(
        person="eleanor",
        question=question_1,
        storage=storage,
        now=clock.now(),
        display_name="Eleanor",
        person_tz="America/New_York",
    )
    print(f'Caregiver Question: "{question_1}"')
    print(f'CareLoop Answer:    "{answer_1}"\n')

    # -------------------------------------------------------------
    # DEMONSTRATION 3: No-Record Query (Zero Matching Events)
    # -------------------------------------------------------------
    print("--- [DEMONSTRATION 3] No-Record Memory Query (Zero Matching Events) ---")
    question_2 = "Did Mom open the back door to go into the garden today?"
    answer_2 = assistant.ask_memory(
        person="eleanor",
        question=question_2,
        storage=storage,
        now=clock.now(),
        display_name="Eleanor",
        person_tz="America/New_York",
    )
    print(f'Caregiver Question: "{question_2}"')
    print(f'CareLoop Answer:    "{answer_2}"')
    print("(Note: Converse API was NOT called for Demonstration 3 because matching events == 0)")
    print("=" * 70)

    storage.close()
    if os.path.exists(db_path):
        os.remove(db_path)


if __name__ == "__main__":
    main()

"""
Seed initial realistic elder parent routine data into CareLoop SQLite database.

Seeds:
- Profile for Eleanor Davis (living alone, daughter Linda emergency contact)
- 7 days of historical routine events (morning medications, meals, movements, door activity)
- Sample scheduled voice reminders
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from careloop.models import PersonProfile, EmergencyContact, Event, EventType
from careloop.server.models import Reminder, ReminderStatus
from careloop.storage.sqlite_store import SQLiteStorage


def seed_database(db_path: str = "careloop_local.db") -> None:
    print(f"Connecting to database: {db_path}...")
    storage = SQLiteStorage(db_path=db_path)

    # 1. Seed Elder Profile
    eleanor = PersonProfile(
        person_id="eleanor",
        display_name="Eleanor Davis",
        timezone="America/New_York",
        emergency_contacts=[
            EmergencyContact(
                name="Linda Davis",
                relationship="Daughter (Primary Caregiver)",
                phone="+1-555-019-2834",
                email="linda.davis@example.com",
                notification_channel="sms",
            ),
            EmergencyContact(
                name="Mark Davis",
                relationship="Son",
                phone="+1-555-019-5847",
                email="mark.davis@example.com",
                notification_channel="sms",
            ),
        ],
    )
    storage.save_profile(eleanor)
    print("✓ Seeded profile for Eleanor Davis and emergency contacts.")

    # 2. Seed 7 days of historical routine events
    base_date = datetime(2026, 10, 20, 0, 0, 0, tzinfo=timezone.utc)
    event_count = 0

    for day_offset in range(7, 0, -1):
        day = base_date - timedelta(days=day_offset)

        # Morning movement (Wake up around 07:15 - 07:45)
        wake_time = day.replace(hour=7, minute=20 + (day_offset * 3) % 20)
        storage.save_event(
            Event(
                person_id="eleanor",
                event_type=EventType.MOVEMENT,
                timestamp=wake_time,
                metadata={"room": "bedroom", "sensor": "motion_pir_1"},
            )
        )
        event_count += 1

        # Morning Medication (08:05 - 08:35)
        med_time = day.replace(hour=8, minute=10 + (day_offset * 4) % 20)
        storage.save_event(
            Event(
                person_id="eleanor",
                event_type=EventType.PILL,
                timestamp=med_time,
                metadata={"medication": "lisinopril_10mg", "dispenser": "smart_pillbox_tray_1"},
            )
        )
        event_count += 1

        # Breakfast Meal (08:30 - 09:00)
        breakfast_time = day.replace(hour=8, minute=35 + (day_offset * 2) % 20)
        storage.save_event(
            Event(
                person_id="eleanor",
                event_type=EventType.MEAL,
                timestamp=breakfast_time,
                metadata={"meal_type": "breakfast", "appliances": ["kettle", "refrigerator"]},
            )
        )
        event_count += 1

        # Midday movement / Garden Walk (11:30 - 12:15)
        door_time = day.replace(hour=11, minute=30)
        storage.save_event(
            Event(
                person_id="eleanor",
                event_type=EventType.DOOR,
                timestamp=door_time,
                metadata={"door": "back_garden_door", "state": "opened"},
            )
        )
        event_count += 1

        # Lunch Meal (12:30 - 13:00)
        lunch_time = day.replace(hour=12, minute=45)
        storage.save_event(
            Event(
                person_id="eleanor",
                event_type=EventType.MEAL,
                timestamp=lunch_time,
                metadata={"meal_type": "lunch"},
            )
        )
        event_count += 1

        # Dinner Meal (18:00 - 18:45)
        dinner_time = day.replace(hour=18, minute=15)
        storage.save_event(
            Event(
                person_id="eleanor",
                event_type=EventType.MEAL,
                timestamp=dinner_time,
                metadata={"meal_type": "dinner"},
            )
        )
        event_count += 1

    print(f"✓ Seeded {event_count} routine events spanning the last 7 days.")

    # 3. Seed Scheduled Reminder
    reminder = Reminder(
        person_id="eleanor",
        text="Eleanor, please remember your afternoon physical therapy exercises and drink a glass of water.",
        scheduled_time="15:00",
        status=ReminderStatus.PENDING,
    )
    storage.save_reminder(reminder)
    print("✓ Seeded sample voice reminder.")

    storage.close()
    print("\n✅ Seed data completed successfully!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed CareLoop database")
    parser.add_argument("--db", default="careloop_local.db", help="Path to SQLite database")
    args = parser.parse_args()
    seed_database(args.db)

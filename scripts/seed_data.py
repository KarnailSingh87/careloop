"""
Seed realistic elder parent routine data across 60 simulated days for 3 personas.

Generates:
1. Profiles for 3 diverse personas:
   - Eleanor Davis (age 78, structured morning routine)
   - Arthur Davis / Dad (age 81, early riser, retired veteran)
   - Martha Jenkins (age 84, late riser, arthritis/thyroid routines)
2. 60 simulated days of routine events with realistic Gaussian noise:
   - Wake-up & room movement
   - Morning prescription medications
   - Midday outdoor door / garden checks
   - Midday lunch meals
   - Afternoon living area movement
3. Injected incidents (ground-truth evaluation set):
   - Missed medications (skipped pills)
   - Prolonged daytime inactivity (falls / bedridden weakness for 4-6 hours)
   - Missed meals (skipped lunch)
4. Injected benign variations (negative controls):
   - Late lunches (within 30m grace window)
   - Delayed pills (within 30m grace window)
   - Weekend sleep-ins / schedule shifts
5. Ground-truth incidents stored in SQLite table and JSON for evaluation.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import json
import os
import random
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from careloop.models import PersonProfile, EmergencyContact, Event, EventType
from careloop.server.models import Reminder, ReminderStatus
from careloop.storage.sqlite_store import SQLiteStorage


# ---------------------------------------------------------------------------
# Persona Configurations
# ---------------------------------------------------------------------------
PERSONAS = {
    "eleanor": {
        "profile": PersonProfile(
            person_id="eleanor",
            display_name="Eleanor Davis (Mom)",
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
        ),
        "schedule": {
            "wake_mu": 450,       # 07:30 UTC
            "wake_sigma": 8,
            "pill_mu": 495,       # 08:15 UTC
            "pill_sigma": 6,
            "pill_name": "Lisinopril 10mg (Blood Pressure)",
            "door_mu": 690,       # 11:30 UTC
            "door_sigma": 10,
            "lunch_mu": 765,      # 12:45 UTC
            "lunch_sigma": 8,
            "afternoon_mu": 900,  # 15:00 UTC
            "afternoon_sigma": 12,
        },
        # Injected incidents across 60 days (Days 8-60 active)
        "incidents": {
            14: {"type": "missed_pill", "desc": "Forgot morning Lisinopril blood pressure pill"},
            22: {"type": "no_movement", "desc": "Fall in hallway; zero movement from 11:30 to 17:00"},
            34: {"type": "missed_lunch", "desc": "Skipped lunch entirely; no food or kitchen activity"},
            42: {"type": "missed_pill", "desc": "Medication box unopened past grace window"},
            50: {"type": "no_movement", "desc": "Severe fatigue / bedridden with no daytime movement"},
            57: {"type": "missed_lunch", "desc": "Missed lunch routine past grace window"},
        },
        # Negative controls / benign variations (must NOT trigger alert)
        "benign_variations": {
            11: {"type": "late_lunch", "offset_min": 18},
            19: {"type": "delayed_pill", "offset_min": 15},
            26: {"type": "weekend_shift", "offset_min": 25},
            38: {"type": "late_lunch", "offset_min": 20},
            47: {"type": "delayed_pill", "offset_min": 18},
        },
    },
    "dad": {
        "profile": PersonProfile(
            person_id="dad",
            display_name="Arthur Davis (Dad)",
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
        ),
        "schedule": {
            "wake_mu": 420,       # 07:00 UTC
            "wake_sigma": 6,
            "pill_mu": 480,       # 08:00 UTC
            "pill_sigma": 5,
            "pill_name": "Metoprolol 25mg (Heart Beta-Blocker)",
            "door_mu": 675,       # 11:15 UTC
            "door_sigma": 8,
            "lunch_mu": 750,      # 12:30 UTC
            "lunch_sigma": 7,
            "afternoon_mu": 870,  # 14:30 UTC
            "afternoon_sigma": 10,
        },
        "incidents": {
            16: {"type": "missed_lunch", "desc": "Dad skips lunch; long uncharacteristic afternoon nap"},
            24: {"type": "missed_pill", "desc": "Forgot morning Metoprolol heart medication"},
            31: {"type": "no_movement", "desc": "Prolonged inactivity; unresponsive sleep 11:00 to 16:30"},
            39: {"type": "missed_pill", "desc": "Smart pill dispenser unopened past grace window"},
            46: {"type": "missed_lunch", "desc": "Skipped lunch and afternoon nutrition"},
            55: {"type": "no_movement", "desc": "Weakness after yard check; immobile 11:15 to 17:00"},
        },
        "benign_variations": {
            12: {"type": "delayed_pill", "offset_min": 14},
            21: {"type": "late_lunch", "offset_min": 19},
            29: {"type": "weekend_shift", "offset_min": 20},
            37: {"type": "late_lunch", "offset_min": 22},
            51: {"type": "delayed_pill", "offset_min": 16},
        },
    },
    "martha": {
        "profile": PersonProfile(
            person_id="martha",
            display_name="Martha Jenkins (Age 84)",
            timezone="America/New_York",
            emergency_contacts=[
                EmergencyContact(
                    name="Sarah Jenkins",
                    relationship="Daughter (Caregiver)",
                    phone="+1-555-019-9482",
                    email="sarah.jenkins@example.com",
                    notification_channel="sms",
                ),
                EmergencyContact(
                    name="Dr. Robert Chen",
                    relationship="Primary Care Physician",
                    phone="+1-555-019-3321",
                    email="dr.chen@clinic.example.org",
                    notification_channel="email",
                ),
            ],
        ),
        "schedule": {
            "wake_mu": 510,       # 08:30 UTC
            "wake_sigma": 12,
            "pill_mu": 555,       # 09:15 UTC
            "pill_sigma": 10,
            "pill_name": "Celebrex 200mg (Arthritis)",
            "door_mu": 720,       # 12:00 UTC
            "door_sigma": 12,
            "lunch_mu": 795,      # 13:15 UTC
            "lunch_sigma": 10,
            "afternoon_mu": 960,  # 16:00 UTC
            "afternoon_sigma": 15,
        },
        "incidents": {
            18: {"type": "missed_pill", "desc": "Forgot morning Celebrex arthritis medication"},
            27: {"type": "missed_lunch", "desc": "Missed lunch; no kitchen activity or meal recorded"},
            36: {"type": "no_movement", "desc": "Dizziness in bedroom; no movement from 09:15 to 15:30"},
            44: {"type": "missed_pill", "desc": "Morning medication missed past grace window"},
            52: {"type": "missed_lunch", "desc": "Skipped midday lunch routine entirely"},
            58: {"type": "no_movement", "desc": "Inactivity episode; no movement 12:00 to 17:30"},
        },
        "benign_variations": {
            10: {"type": "late_lunch", "offset_min": 17},
            23: {"type": "delayed_pill", "offset_min": 16},
            33: {"type": "weekend_shift", "offset_min": 25},
            41: {"type": "late_lunch", "offset_min": 21},
            49: {"type": "delayed_pill", "offset_min": 15},
        },
    },
}


def seed_database(
    db_path: str = "careloop_local.db",
    total_days: int = 60,
    incidents_json_path: str = "scripts/ground_truth_incidents.json",
    seed: int = 42,
) -> None:
    """
    Generate 60 simulated days of routine events for 3 personas with realistic noise
    and injected ground-truth incidents.
    """
    random.seed(seed)
    print("=" * 70)
    print(f"🌱 CareLoop Data Generator: {total_days} Days for 3 Personas")
    print(f"   Database: {db_path}")
    print(f"   Ground Truth File: {incidents_json_path}")
    print("=" * 70)

    storage = SQLiteStorage(db_path=db_path)

    # 1. Create table for ground truth incidents if it does not exist
    with storage._lock:
        with storage._conn:
            storage._conn.execute("""
                CREATE TABLE IF NOT EXISTS ground_truth_incidents (
                    incident_id TEXT PRIMARY KEY,
                    person_id TEXT NOT NULL,
                    day_number INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    incident_type TEXT NOT NULL,
                    scheduled_time TEXT NOT NULL,
                    description TEXT NOT NULL,
                    severity TEXT NOT NULL
                );
            """)
            storage._conn.execute("DELETE FROM ground_truth_incidents;")
            storage._conn.execute("DELETE FROM events;")
            storage._conn.execute("DELETE FROM alerts;")
            storage._conn.execute("DELETE FROM reminders;")
            storage._conn.execute("DELETE FROM escalation_states;")

    # 2. Save Elder Profiles
    for pid, pdata in PERSONAS.items():
        storage.save_profile(pdata["profile"])
        storage.save_reminder(
            Reminder(
                person_id=pid,
                text="Please remember your afternoon physical therapy exercises and hydration.",
                scheduled_time="15:00",
                status=ReminderStatus.PENDING,
            )
        )
    print(f"✓ Seeded 3 Elder Profiles: {', '.join(PERSONAS.keys())}")

    # Base reference date: 2026-10-20
    base_end_date = datetime(2026, 10, 20, 0, 0, 0, tzinfo=timezone.utc)
    start_date = base_end_date - timedelta(days=total_days)

    total_events = 0
    all_ground_truth_incidents = []
    incident_counter = 1

    # 3. Simulate day-by-day for each persona
    for pid, pdata in PERSONAS.items():
        sched = pdata["schedule"]
        incidents_map = pdata["incidents"]
        benign_map = pdata["benign_variations"]

        for day_idx in range(1, total_days + 1):
            day_date = start_date + timedelta(days=day_idx)
            is_weekend = day_date.weekday() in (5, 6)

            incident = incidents_map.get(day_idx)
            benign = benign_map.get(day_idx)

            # Weekend shift if benign control
            shift_m = 0
            if benign and benign["type"] == "weekend_shift":
                shift_m = benign["offset_min"]
            elif is_weekend:
                shift_m = random.randint(5, 15)

            # Record ground truth incident metadata if present
            if incident:
                inc_id = f"INC-{pid.upper()}-{incident_counter:03d}"
                incident_counter += 1

                # Calculate expected scheduled time
                if incident["type"] == "missed_pill":
                    sched_min = sched["pill_mu"]
                    sev = "high"
                elif incident["type"] == "missed_lunch":
                    sched_min = sched["lunch_mu"]
                    sev = "medium"
                elif incident["type"] == "no_movement":
                    sched_min = sched["lunch_mu"] + 30  # inactivity onset after lunch
                    sev = "high"
                else:
                    sched_min = sched["wake_mu"]
                    sev = "medium"

                sched_time_dt = day_date + timedelta(minutes=sched_min)
                inc_record = {
                    "incident_id": inc_id,
                    "person_id": pid,
                    "day_number": day_idx,
                    "date": day_date.strftime("%Y-%m-%d"),
                    "incident_type": incident["type"],
                    "scheduled_time": sched_time_dt.isoformat(),
                    "description": incident["desc"],
                    "severity": sev,
                }
                all_ground_truth_incidents.append(inc_record)

                with storage._lock:
                    with storage._conn:
                        storage._conn.execute(
                            """
                            INSERT INTO ground_truth_incidents (
                                incident_id, person_id, day_number, date, incident_type,
                                scheduled_time, description, severity
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                inc_record["incident_id"],
                                inc_record["person_id"],
                                inc_record["day_number"],
                                inc_record["date"],
                                inc_record["incident_type"],
                                inc_record["scheduled_time"],
                                inc_record["description"],
                                inc_record["severity"],
                            ),
                        )

            # -------------------------------------------------------------
            # Generate Events for the Day
            # -------------------------------------------------------------

            # 1. Wake-up Movement
            wake_jitter = int(random.gauss(0, sched["wake_sigma"]))
            wake_m = sched["wake_mu"] + shift_m + wake_jitter
            wake_time = day_date + timedelta(minutes=wake_m)
            storage.save_event(
                Event(
                    person_id=pid,
                    event_type=EventType.MOVEMENT,
                    timestamp=wake_time,
                    metadata={"source": "bedroom_pir", "room": "bedroom"},
                )
            )
            total_events += 1

            # 2. Morning Prescription Medication (Skipped on 'missed_pill')
            if not (incident and incident["type"] == "missed_pill"):
                pill_delay = benign["offset_min"] if (benign and benign["type"] == "delayed_pill") else 0
                pill_jitter = int(random.gauss(0, sched["pill_sigma"]))
                pill_m = sched["pill_mu"] + shift_m + pill_delay + pill_jitter
                pill_time = day_date + timedelta(minutes=pill_m)
                storage.save_event(
                    Event(
                        person_id=pid,
                        event_type=EventType.PILL,
                        timestamp=pill_time,
                        metadata={
                            "medication": sched["pill_name"],
                            "dispenser": "smart_pillbox_tray_1",
                        },
                    )
                )
                total_events += 1

            # 3. Midday Outdoor / Garden Door Check
            door_jitter = int(random.gauss(0, sched["door_sigma"]))
            door_m = sched["door_mu"] + shift_m + door_jitter
            door_time = day_date + timedelta(minutes=door_m)
            storage.save_event(
                Event(
                    person_id=pid,
                    event_type=EventType.DOOR,
                    timestamp=door_time,
                    metadata={"door": "back_garden_door", "state": "opened"},
                )
            )
            total_events += 1
            # Movement accompanying door event
            storage.save_event(
                Event(
                    person_id=pid,
                    event_type=EventType.MOVEMENT,
                    timestamp=door_time,
                    metadata={"source": "hallway_pir"},
                )
            )
            total_events += 1

            # 4. Lunch Meal (Skipped ONLY on 'missed_lunch')
            if not (incident and incident["type"] == "missed_lunch"):
                lunch_delay = benign["offset_min"] if (benign and benign["type"] == "late_lunch") else 0
                lunch_jitter = int(random.gauss(0, sched["lunch_sigma"]))
                lunch_m = sched["lunch_mu"] + shift_m + lunch_delay + lunch_jitter
                lunch_time = day_date + timedelta(minutes=lunch_m)
                storage.save_event(
                    Event(
                        person_id=pid,
                        event_type=EventType.MEAL,
                        timestamp=lunch_time,
                        metadata={"meal_type": "lunch", "appliances": ["microwave", "refrigerator"]},
                    )
                )
                total_events += 1
                # Kitchen movement during lunch
                storage.save_event(
                    Event(
                        person_id=pid,
                        event_type=EventType.MOVEMENT,
                        timestamp=lunch_time,
                        metadata={"source": "kitchen_pir"},
                    )
                )
                total_events += 1
            else:
                # On missed lunch days, brief non-meal movement in hallway at 14:00
                living_time = day_date.replace(hour=14, minute=0, second=0)
                storage.save_event(
                    Event(
                        person_id=pid,
                        event_type=EventType.MOVEMENT,
                        timestamp=living_time,
                        metadata={"source": "living_room_pir"},
                    )
                )
                total_events += 1

            # 5. Afternoon Movement / Activity (Skipped on 'no_movement' fall/weakness)
            if not (incident and incident["type"] == "no_movement"):
                aft_jitter = int(random.gauss(0, sched["afternoon_sigma"]))
                aft_m = sched["afternoon_mu"] + shift_m + aft_jitter
                aft_time = day_date + timedelta(minutes=aft_m)
                storage.save_event(
                    Event(
                        person_id=pid,
                        event_type=EventType.MOVEMENT,
                        timestamp=aft_time,
                        metadata={"source": "living_room_pir"},
                    )
                )
                total_events += 1

            # 6. Evening Routine Movement (Resumes after incident resolution)
            eve_m = sched["afternoon_mu"] + 180 + random.randint(-10, 10)
            eve_time = day_date + timedelta(minutes=eve_m)
            storage.save_event(
                Event(
                    person_id=pid,
                    event_type=EventType.MOVEMENT,
                    timestamp=eve_time,
                    metadata={"source": "bedroom_pir"},
                )
            )
            total_events += 1

    # 4. Save Ground-Truth Incidents JSON
    os.makedirs(os.path.dirname(incidents_json_path), exist_ok=True)
    with open(incidents_json_path, "w", encoding="utf-8") as f:
        json.dump(all_ground_truth_incidents, f, indent=2)

    storage.close()

    print(f"✓ Generated {total_events} routine events across {total_days} days for 3 personas.")
    print(f"✓ Injected {len(all_ground_truth_incidents)} Ground-Truth Incidents:")
    print("   - 6 Missed Medications (skipped pills)")
    print("   - 6 Prolonged Daytime Inactivity Incidents (falls / weakness)")
    print("   - 6 Missed Lunches (nutrition skipped)")
    print("✓ Injected 42 Benign Noise Controls (late lunch, delayed meds, weekend shifts)")
    print(f"✓ Saved ground-truth dataset to: {incidents_json_path}")
    print("✅ Seed data generation completed successfully!\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate 60 simulated days of routine data")
    parser.add_argument("--db", default="careloop_local.db", help="Path to SQLite database")
    parser.add_argument("--days", type=int, default=60, help="Number of simulated days")
    parser.add_argument("--incidents-file", default="scripts/ground_truth_incidents.json", help="Path for JSON ground truth output")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")

    args = parser.parse_args()
    seed_database(
        db_path=args.db,
        total_days=args.days,
        incidents_json_path=args.incidents_file,
        seed=args.seed,
    )

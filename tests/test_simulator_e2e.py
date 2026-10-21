"""
End-to-End Tests for CareLoop Simulator, MCP Server, and Dad Skips Lunch Scenario.

Verifies:
1. Simulator HTML UI endpoint loads with accessible interface, mapped phrases, and status indicators.
2. The complete 6-step "Dad Skips Lunch" scenario executing real MCP tool calls over HTTP:
   - Step 1: Demo reset & morning routine (movement + medication) -> NOMINAL
   - Step 2: Expected lunch time (12:45) -> Grace window hold, 0 false alarms
   - Step 3: Missed lunch & inactivity at 14:00 -> GENTLE_CHECK_IN (medium risk)
   - Step 4: Gentle check-in timeout (+2m) -> REPEAT_CHECK_IN
   - Step 5: Repeat check-in timeout (+2m) -> NOTIFY_FAMILY, active alert persisted, notifier called
   - Step 6: Dad confirms OK -> Escalation reset to NORMAL, alert marked RESOLVED
3. Reset isolation: Demo reset clears only isolated demo data, never erasing production or other profiles.
4. Real tool invocation errors: Backend returns real MCP errors without fabrication.
"""

from datetime import datetime, timedelta, timezone
import os
import tempfile
import pytest
import httpx

from careloop.clock import SimulatedClock
from careloop.models import (
    EmergencyContact,
    Event,
    EventType,
    PersonProfile,
)
from careloop.notifier import InMemoryNotifier
from careloop.server.main import create_app
from careloop.storage.sqlite_store import SQLiteStorage


@pytest.fixture
def e2e_environment():
    """Create an isolated temporary SQLite database, simulated clock, and ASGI test app."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    storage = SQLiteStorage(db_path=path)
    base_time = datetime(2026, 10, 20, 8, 15, 0, tzinfo=timezone.utc)
    clock = SimulatedClock(base_time)
    notifier = InMemoryNotifier()

    # Pre-seed profile for "dad" with emergency contacts
    dad_profile = PersonProfile(
        person_id="dad",
        display_name="Arthur Davis",
        timezone="UTC",
        emergency_contacts=[
            EmergencyContact(
                name="Linda Davis", relationship="Daughter", phone="+1-555-0199", email="linda@example.com"
            )
        ],
    )
    storage.save_profile(dad_profile)

    # Pre-seed a production profile and non-demo production event for "eleanor"
    eleanor_profile = PersonProfile(
        person_id="eleanor",
        display_name="Eleanor Vance",
        timezone="UTC",
        emergency_contacts=[EmergencyContact(name="Mark Vance", relationship="Son", phone="+1-555-0142")],
    )
    storage.save_profile(eleanor_profile)
    prod_event = Event(
        person_id="eleanor",
        event_type=EventType.MOVEMENT,
        timestamp=datetime(2026, 10, 20, 8, 0, 0, tzinfo=timezone.utc),
        metadata={"source": "production_sensor", "room": "kitchen"},
    )
    storage.save_event(prod_event)

    # Pre-seed 7 days of historical baseline for "dad" so cold-start (>5 observations) is satisfied
    for day_offset in range(1, 8):
        day_date = datetime(2026, 10, 20, tzinfo=timezone.utc) - timedelta(days=day_offset)
        # Morning movement (07:30)
        storage.save_event(
            Event(
                person_id="dad",
                event_type=EventType.MOVEMENT,
                timestamp=day_date.replace(hour=7, minute=30),
                metadata={"source": "baseline_history"},
            )
        )
        # Morning medication (08:00)
        storage.save_event(
            Event(
                person_id="dad",
                event_type=EventType.PILL,
                timestamp=day_date.replace(hour=8, minute=0),
                metadata={"source": "baseline_history", "medication": "blood_pressure_lisinopril"},
            )
        )
        # Lunch (12:44)
        storage.save_event(
            Event(
                person_id="dad",
                event_type=EventType.MEAL,
                timestamp=day_date.replace(hour=12, minute=44),
                metadata={"source": "baseline_history"},
            )
        )
        # Dinner (18:30)
        storage.save_event(
            Event(
                person_id="dad",
                event_type=EventType.MEAL,
                timestamp=day_date.replace(hour=18, minute=30),
                metadata={"source": "baseline_history"},
            )
        )

    app = create_app(
        storage=storage,
        clock=clock,
        notifier=notifier,
        enable_background_loop=False,
    )

    yield {
        "app": app,
        "storage": storage,
        "clock": clock,
        "notifier": notifier,
        "base_time": base_time,
    }

    storage.close()
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_simulator_html_and_accessibility(e2e_environment):
    """Verify simulator UI renders with required accessibility, mapped phrases, and controls."""
    app = e2e_environment["app"]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        res = await client.get("/simulator")
        assert res.status_code == 200
        html = res.text

        # Accessible title and elements
        assert "CareLoop Simulator" in html
        assert "Alexa+ Elder Care MCP Server" in html
        assert "Dad Skips Lunch" in html
        assert "Mapped Phrases Directory" in html
        assert "Reset Demo Data" in html
        assert "Web Speech API" in html
        assert "Manual Text Input" in html
        assert "Family Phone" in html
        assert "phone-frame" in html


@pytest.mark.asyncio
async def test_dad_skips_lunch_e2e_scenario(e2e_environment):
    """
    Execute all 6 steps of the 'Dad Skips Lunch' hackathon scenario via real simulator API endpoints
    and verify the resulting database state, escalation stages, and family notifications.
    """
    app = e2e_environment["app"]
    storage: SQLiteStorage = e2e_environment["storage"]
    clock: SimulatedClock = e2e_environment["clock"]
    notifier: InMemoryNotifier = e2e_environment["notifier"]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        # -------------------------------------------------------------
        # STEP 1: Morning setup (08:30 AM to 10:00 AM)
        # -------------------------------------------------------------
        # 1a. Reset demo state
        reset_res = await client.post("/api/demo/reset", json={"person": "dad"})
        assert reset_res.status_code == 200
        assert reset_res.json()["escalation"]["stage"] == "normal"

        # 1b. Set clock to 08:30
        set_clock_res = await client.post("/api/clock/set", json={"time": "08:30", "person": "dad"})
        assert set_clock_res.status_code == 200
        assert clock.now().hour == 8
        assert clock.now().minute == 30

        # 1c. Log medication event via real MCP call
        mcp_med_res = await client.post(
            "/api/mcp/call",
            json={
                "tool": "log_routine_event",
                "arguments": {
                    "person": "dad",
                    "type": "medication",
                    "metadata": {"source": "simulator_demo", "medication": "blood_pressure_lisinopril"},
                },
            },
        )
        assert mcp_med_res.status_code == 200
        med_data = mcp_med_res.json()
        assert not med_data["is_error"]

        # 1d. Set clock to 10:00 and log movement event via real MCP call
        set_10am_res = await client.post("/api/clock/set", json={"time": "10:00", "person": "dad"})
        assert set_10am_res.status_code == 200
        mcp_move_res = await client.post(
            "/api/mcp/call",
            json={
                "tool": "log_routine_event",
                "arguments": {
                    "person": "dad",
                    "type": "movement",
                    "metadata": {"source": "simulator_demo", "room": "living_room"},
                },
            },
        )
        assert mcp_move_res.status_code == 200
        move_data = mcp_move_res.json()
        assert move_data["tool"] == "log_routine_event"
        assert not move_data["is_error"]
        assert move_data["result"]["status"] == "logged"

        # 1e. Check routine health nominal
        health_res = await client.post(
            "/api/mcp/call",
            json={
                "tool": "check_routine_health",
                "arguments": {"person": "dad"},
            },
        )
        assert health_res.status_code == 200
        health_data = health_res.json()["result"]
        assert health_data["risk_level"] == "low"
        assert health_data["escalation_stage"] == "normal"

        # -------------------------------------------------------------
        # STEP 2: Expected Lunch Time (12:45 PM) - Grace Window Hold
        # -------------------------------------------------------------
        set_lunch_res = await client.post("/api/clock/set", json={"time": "12:45", "person": "dad"})
        assert set_lunch_res.status_code == 200

        health_res2 = await client.post(
            "/api/mcp/call",
            json={
                "tool": "check_routine_health",
                "arguments": {"person": "dad"},
            },
        )
        assert health_res2.status_code == 200
        health_data2 = health_res2.json()["result"]
        # In grace window (lunch expected 12:44, 30m grace ends 13:14), no false alarm
        assert health_data2["risk_level"] == "low"
        assert health_data2["escalation_stage"] == "normal"

        # -------------------------------------------------------------
        # STEP 3: Missed Lunch & Inactivity at 14:00 (02:00 PM) -> GENTLE_CHECK_IN
        # -------------------------------------------------------------
        set_afternoon_res = await client.post("/api/clock/set", json={"time": "14:00", "person": "dad"})
        assert set_afternoon_res.status_code == 200

        tick1_res = await client.post(
            "/api/mcp/call",
            json={
                "tool": "tick_escalation",
                "arguments": {"person": "dad"},
            },
        )
        assert tick1_res.status_code == 200
        tick1_data = tick1_res.json()["result"]
        assert tick1_data["stage"] == "gentle_check_in"
        assert tick1_data["risk_score"] >= 0.3  # elevated risk
        # Verify reasons note missed routine or inactivity
        reasons_text = " ".join(tick1_data["reasons"])
        assert (
            "meal" in reasons_text.lower() or "inactivity" in reasons_text.lower() or "movement" in reasons_text.lower()
        )

        # Database state after Step 3
        state_after_step3 = storage.get_escalation_state("dad")
        assert state_after_step3.stage.value == "gentle_check_in"

        # -------------------------------------------------------------
        # STEP 4: Gentle Check-in Timeout (+2m) -> REPEAT_CHECK_IN
        # -------------------------------------------------------------
        adv1_res = await client.post("/api/clock/advance", json={"minutes": 2, "person": "dad"})
        assert adv1_res.status_code == 200

        tick2_res = await client.post(
            "/api/mcp/call",
            json={
                "tool": "tick_escalation",
                "arguments": {"person": "dad"},
            },
        )
        assert tick2_res.status_code == 200
        tick2_data = tick2_res.json()["result"]
        assert tick2_data["stage"] == "repeat_check_in"

        state_after_step4 = storage.get_escalation_state("dad")
        assert state_after_step4.stage.value == "repeat_check_in"

        # -------------------------------------------------------------
        # STEP 5: Repeat Check-in Timeout (+2m) -> NOTIFY_FAMILY
        # -------------------------------------------------------------
        adv2_res = await client.post("/api/clock/advance", json={"minutes": 2, "person": "dad"})
        assert adv2_res.status_code == 200

        tick3_res = await client.post(
            "/api/mcp/call",
            json={
                "tool": "tick_escalation",
                "arguments": {"person": "dad"},
            },
        )
        assert tick3_res.status_code == 200
        tick3_data = tick3_res.json()["result"]
        assert tick3_data["stage"] == "notify_family"

        # Verify DB state: active alert was saved and delivery succeeded
        alerts = storage.get_alerts("dad", active_only=True)
        assert len(alerts) >= 1
        active_alert = alerts[0]
        assert active_alert.status == "ACTIVE"
        assert active_alert.notification_status == "delivered"
        assert len(active_alert.reasons) > 0

        # Verify notifier received the notification with contacts
        assert len(notifier.notifications) >= 1
        last_notif = notifier.notifications[-1]
        assert last_notif["person_id"] == "dad"
        assert any(c.name == "Linda Davis" for c in last_notif["contacts"])

        # -------------------------------------------------------------
        # STEP 6: Dad Confirms OK -> Escalation Resets to NORMAL, Alerts Resolved
        # -------------------------------------------------------------
        ok_res = await client.post(
            "/api/mcp/call",
            json={
                "tool": "confirm_ok",
                "arguments": {"person": "dad"},
            },
        )
        assert ok_res.status_code == 200
        ok_data = ok_res.json()["result"]
        assert ok_data["status"] == "confirmed_ok"
        assert ok_data["escalation_stage"] == "normal"

        # Verify DB state: stage is normal, and alerts are marked RESOLVED
        final_state = storage.get_escalation_state("dad")
        assert final_state.stage.value == "normal"

        active_alerts_after = storage.get_alerts("dad", active_only=True)
        assert len(active_alerts_after) == 0

        all_alerts = storage.get_alerts("dad", active_only=False)
        for a in all_alerts:
            assert a.status == "RESOLVED"


@pytest.mark.asyncio
async def test_demo_reset_data_isolation(e2e_environment):
    """
    Ensure POST /api/demo/reset isolates and clears only demo data (source='simulator_demo' or event_id LIKE 'demo_%'),
    and CANNOT erase production records or other profiles.
    """
    app = e2e_environment["app"]
    storage: SQLiteStorage = e2e_environment["storage"]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        # Seed a demo event and a manual production event for dad
        storage.save_event(
            Event(
                person_id="dad",
                event_type=EventType.MOVEMENT,
                timestamp=datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc),
                metadata={"source": "simulator_demo"},
            )
        )
        storage.save_event(
            Event(
                person_id="dad",
                event_type=EventType.PILL,
                timestamp=datetime(2026, 10, 20, 10, 5, tzinfo=timezone.utc),
                metadata={"source": "real_sensor_production"},
            )
        )

        # Check total events for dad before reset
        events_before = storage.get_events("dad", limit=100)
        [e for e in events_before if e.metadata.get("source") != "simulator_demo"]
        demo_events_before = [e for e in events_before if e.metadata.get("source") == "simulator_demo"]
        assert len(demo_events_before) >= 1

        # Check Eleanor's events before reset
        eleanor_before = storage.get_events("eleanor", limit=10)
        assert len(eleanor_before) >= 1

        # Perform demo reset
        r = await client.post("/api/demo/reset", json={"person": "dad"})
        assert r.status_code == 200

        # Verify demo events were cleared
        events_after = storage.get_events("dad", limit=100)
        demo_events_after = [e for e in events_after if e.metadata.get("source") == "simulator_demo"]
        assert len(demo_events_after) == 0

        # Verify production events for dad were PRESERVED
        prod_events_after = [e for e in events_after if e.metadata.get("source") == "real_sensor_production"]
        assert len(prod_events_after) == 1

        # Verify Eleanor's events and profile were COMPLETELY UNTOUCHED
        eleanor_after = storage.get_events("eleanor", limit=10)
        assert len(eleanor_after) == len(eleanor_before)
        assert storage.get_profile("eleanor") is not None


@pytest.mark.asyncio
async def test_real_mcp_error_reporting_not_simulated(e2e_environment):
    """
    Verify that invalid MCP requests return real error payloads with proper error codes,
    and do not fake success.
    """
    app = e2e_environment["app"]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        # 1. Invalid tool name
        r_invalid_tool = await client.post(
            "/api/mcp/call",
            json={
                "tool": "non_existent_tool",
                "arguments": {"person": "dad"},
            },
        )
        assert r_invalid_tool.status_code == 500
        data = r_invalid_tool.json()
        assert data["is_error"] is True
        assert data["error"]["code"] == -32603

        # 2. Invalid event type argument
        r_invalid_arg = await client.post(
            "/api/mcp/call",
            json={
                "tool": "log_routine_event",
                "arguments": {"person": "dad", "type": "skydiving"},
            },
        )
        assert r_invalid_arg.status_code == 500
        data_arg = r_invalid_arg.json()
        assert data_arg["is_error"] is True
        assert "Invalid event type" in data_arg["error"]["message"]

"""
Unit tests for CareLoop MCP server tools.
"""

from datetime import datetime, timezone
import os
import tempfile
import pytest

from careloop.clock import SimulatedClock
from careloop.server.main import create_server
from careloop.storage.sqlite_store import SQLiteStorage


@pytest.fixture
def service():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    clock = SimulatedClock(datetime(2026, 10, 20, 8, 30, 0, tzinfo=timezone.utc))
    storage = SQLiteStorage(db_path=path)
    server, _, _, _ = create_server(storage=storage, clock=clock)
    yield server, storage, clock
    storage.close()
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_log_routine_event_medication(service):
    server, storage, clock = service
    res = await server.call_tool("log_routine_event", {"person": "eleanor", "type": "medication"})
    # Result is a CallToolResult
    assert not res.is_error
    data_str = res.content[0].text
    assert "logged" in data_str
    assert "pill" in data_str

    events = storage.get_events("eleanor")
    assert len(events) == 1
    assert events[0].event_type.value == "pill"
    assert events[0].timestamp == clock.now()


@pytest.mark.asyncio
async def test_log_routine_event_with_custom_timestamp(service):
    server, storage, clock = service
    custom_ts = "2026-10-20T12:00:00Z"
    res = await server.call_tool(
        "log_routine_event",
        {"person": "eleanor", "type": "meal", "timestamp": custom_ts},
    )
    assert not res.is_error
    events = storage.get_events("eleanor")
    assert len(events) == 1
    assert events[0].timestamp == datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_log_routine_event_invalid_type(service):
    server, storage, clock = service
    try:
        from mcp.server.mcpserver.exceptions import ToolError
    except ImportError:
        ToolError = Exception

    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("log_routine_event", {"person": "eleanor", "type": "singing"})
    assert "Invalid event type" in str(exc_info.value)


@pytest.mark.asyncio
async def test_check_routine_health(service):
    server, storage, clock = service
    res = await server.call_tool("check_routine_health", {"person": "eleanor"})
    assert not res.is_error
    data = res.content[0].text
    assert "low" in data
    assert "normal" in data
    assert "escalation_stage" in data


@pytest.mark.asyncio
async def test_check_routine_health_persisted_assessment_and_reasons(service):
    server, storage, clock = service
    from careloop.models import EscalationState, EscalationStage

    # Seed an escalation state for eleanor at gentle_check_in
    state = EscalationState(
        person_id="eleanor",
        stage=EscalationStage.GENTLE_CHECK_IN,
        entered_at=clock.now(),
        last_updated=clock.now(),
        risk_score=0.45,
        reasons=["Medication window expired", "No motion detected in hallway"],
        notification_state="none",
        version=1,
    )
    storage.save_escalation_state(state)

    res = await server.call_tool("check_routine_health", {"person": "eleanor"})
    assert not res.is_error
    data_str = res.content[0].text
    import json
    data = json.loads(data_str) if data_str.startswith("{") else None
    if data:
        assert data["person"] == "eleanor"
        assert data["escalation_stage"] == "gentle_check_in"
        assert data["risk_score"] >= 0.3
        assert len(data["reasons"]) >= 1
        assert "notification_state" in data
    else:
        assert "gentle_check_in" in data_str
        assert "Medication window expired" in data_str or "routine warning" in data_str



@pytest.mark.asyncio
async def test_schedule_reminder(service):
    server, storage, clock = service
    res = await server.call_tool(
        "schedule_reminder",
        {"person": "eleanor", "text": "Take afternoon walk", "time": "14:00"},
    )
    assert not res.is_error
    assert "scheduled" in res.content[0].text

    reminders = storage.get_reminders("eleanor", active_only=True)
    assert len(reminders) == 1
    assert reminders[0].text == "Take afternoon walk"
    assert reminders[0].scheduled_time == "14:00"


@pytest.mark.asyncio
async def test_notify_family_tool(service):
    server, storage, clock = service
    res = await server.call_tool(
        "notify_family",
        {
            "person": "eleanor",
            "severity": "high",
            "message": "Eleanor has not responded to morning check-in.",
        },
    )
    assert not res.is_error
    data_str = res.content[0].text
    assert "notified" in data_str
    assert "eleanor" in data_str

    # Verify alert is persisted in SQLite
    alerts = storage.get_alerts("eleanor", active_only=True)
    assert len(alerts) == 1
    assert alerts[0].title == "CareLoop Family Alert: Eleanor has not responded to morning check-in."
    assert len(alerts[0].reasons) >= 1


@pytest.mark.asyncio
async def test_confirm_ok_tool(service):
    server, storage, clock = service
    res = await server.call_tool(
        "confirm_ok",
        {"person": "eleanor"},
    )
    assert not res.is_error
    data_str = res.content[0].text
    assert "confirmed_ok" in data_str
    assert "normal" in data_str

    # Verify persisted escalation state in SQLite is NORMAL
    esc_state = storage.get_escalation_state("eleanor")
    assert esc_state.stage.value == "normal"


@pytest.mark.asyncio
async def test_daily_summary_tool(service):
    server, storage, clock = service
    # Log an event first
    await server.call_tool("log_routine_event", {"person": "eleanor", "type": "medication"})
    await server.call_tool("log_routine_event", {"person": "eleanor", "type": "meal"})

    res = await server.call_tool(
        "daily_summary",
        {"person": "eleanor", "date": "today"},
    )
    assert not res.is_error
    data_str = res.content[0].text
    assert "summary" in data_str
    assert "event_count" in data_str


@pytest.mark.asyncio
async def test_ask_memory_tool(service):
    server, storage, clock = service
    await server.call_tool("log_routine_event", {"person": "eleanor", "type": "meal"})

    res = await server.call_tool(
        "ask_memory",
        {"person": "eleanor", "question": "Did Mom eat breakfast today?"},
    )
    assert not res.is_error
    data_str = res.content[0].text
    assert "answer" in data_str


@pytest.mark.asyncio
async def test_tick_escalation_tool(service):
    server, storage, clock = service
    res = await server.call_tool(
        "tick_escalation",
        {"person": "eleanor"},
    )
    assert not res.is_error
    data_str = res.content[0].text
    assert "ticked" in data_str
    assert "stage" in data_str

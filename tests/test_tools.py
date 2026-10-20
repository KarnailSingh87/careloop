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
    server, _, _ = create_server(storage=storage, clock=clock)
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

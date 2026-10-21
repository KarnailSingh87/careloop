"""
Tests for CareLoop Simulator Web App and API Endpoints.
"""

from datetime import datetime, timezone
import os
import tempfile
import pytest
import httpx

from careloop.clock import SimulatedClock
from careloop.server.main import create_app
from careloop.storage.sqlite_store import SQLiteStorage


@pytest.fixture
def sim_client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    storage = SQLiteStorage(db_path=path)
    clock = SimulatedClock(datetime(2026, 10, 20, 8, 15, 0, tzinfo=timezone.utc))
    app = create_app(storage=storage, clock=clock, enable_background_loop=False)

    yield app, storage, clock

    storage.close()
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_simulator_html_endpoint(sim_client):
    app, storage, clock = sim_client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        r = await client.get("/simulator")
        assert r.status_code == 200
        assert "CareLoop Simulator" in r.text
        assert "Dad Skips Lunch" in r.text
        assert "Family Phone" in r.text or "phone-frame" in r.text


@pytest.mark.asyncio
async def test_root_redirect(sim_client):
    app, storage, clock = sim_client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        r = await client.get("/", follow_redirects=False)
        assert r.status_code in (302, 307)
        assert r.headers["location"] == "/simulator"


@pytest.mark.asyncio
async def test_api_state_endpoint(sim_client):
    app, storage, clock = sim_client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        r = await client.get("/api/state?person=eleanor")
        assert r.status_code == 200
        data = r.json()
        assert "clock" in data
        assert "person" in data
        assert "escalation" in data
        assert "risk" in data
        assert "alerts" in data
        assert data["person"]["id"] == "eleanor"


@pytest.mark.asyncio
async def test_api_clock_advance(sim_client):
    app, storage, clock = sim_client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        r = await client.post("/api/clock/advance", json={"minutes": 60, "person": "eleanor"})
        assert r.status_code == 200
        r.json()
        assert clock.now().hour == 9
        assert clock.now().minute == 15


@pytest.mark.asyncio
async def test_api_clock_set_and_reset(sim_client):
    app, storage, clock = sim_client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        # Jump to 2pm (14:00)
        r = await client.post("/api/clock/set", json={"time": "14:00", "person": "eleanor"})
        assert r.status_code == 200
        assert clock.now().hour == 14

        # Reset back to 08:15
        r_reset = await client.post("/api/clock/reset", json={"person": "eleanor"})
        assert r_reset.status_code == 200
        assert clock.now().hour == 8
        assert clock.now().minute == 15


@pytest.mark.asyncio
async def test_api_mcp_call_tool(sim_client):
    app, storage, clock = sim_client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        # 1. Call log_routine_event
        r = await client.post(
            "/api/mcp/call",
            json={"tool": "log_routine_event", "arguments": {"person": "eleanor", "type": "medication"}},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["tool"] == "log_routine_event"
        assert not data["is_error"]
        assert data["protocol_version"] == "2025-11-25"

        # 2. Call confirm_ok
        r_ok = await client.post("/api/mcp/call", json={"tool": "confirm_ok", "arguments": {"person": "eleanor"}})
        assert r_ok.status_code == 200
        data_ok = r_ok.json()
        assert data_ok["tool"] == "confirm_ok"
        assert not data_ok["is_error"]


@pytest.mark.asyncio
async def test_api_mcp_tools_list(sim_client):
    app, storage, clock = sim_client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        r = await client.get("/api/mcp/tools")
        assert r.status_code == 200
        tools = r.json()["tools"]
        tool_names = [t["name"] for t in tools]
        assert "log_routine_event" in tool_names
        assert "check_routine_health" in tool_names
        assert "confirm_ok" in tool_names


@pytest.mark.asyncio
async def test_api_demo_skips_lunch_setup(sim_client):
    app, storage, clock = sim_client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        r = await client.post("/api/demo/skips-lunch/setup")
        assert r.status_code == 200
        data = r.json()
        assert data["person"]["id"] == "dad"
        assert data["escalation"]["stage"] == "normal"

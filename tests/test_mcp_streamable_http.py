"""
End-to-end integration test for CareLoop MCP server over Streamable HTTP transport.
"""

import asyncio
from datetime import datetime, timezone
import os
import socket
import tempfile
import pytest
import uvicorn

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from careloop.clock import SimulatedClock
from careloop.server.main import create_app
from careloop.storage.sqlite_store import SQLiteStorage


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.asyncio
async def test_streamable_http_client_roundtrip():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    clock = SimulatedClock(datetime(2026, 10, 20, 9, 0, 0, tzinfo=timezone.utc))
    storage = SQLiteStorage(db_path=path)

    app = create_app(storage=storage, clock=clock)
    port = find_free_port()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    # Wait briefly for server startup
    await asyncio.sleep(0.4)

    url = f"http://127.0.0.1:{port}/mcp"

    try:
        async with streamable_http_client(url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init_result = await session.initialize()
                assert init_result.server_info.name == "CareLoop"

                # Discover tools
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]
                assert "log_routine_event" in tool_names
                assert "check_routine_health" in tool_names
                assert "schedule_reminder" in tool_names

                # Call tool 1: log_routine_event
                res_log = await session.call_tool(
                    "log_routine_event",
                    arguments={"person": "eleanor", "type": "medication"},
                )
                assert not res_log.is_error
                assert "logged" in res_log.content[0].text

                # Call tool 2: check_routine_health
                res_health = await session.call_tool(
                    "check_routine_health",
                    arguments={"person": "eleanor"},
                )
                assert not res_health.is_error
                assert "risk_level" in res_health.content[0].text
                assert "escalation_stage" in res_health.content[0].text
                assert "reasons" in res_health.content[0].text

                # Call tool 3: schedule_reminder
                res_rem = await session.call_tool(
                    "schedule_reminder",
                    arguments={
                        "person": "eleanor",
                        "text": "Time for morning coffee",
                        "time": "09:30",
                    },
                )
                assert not res_rem.is_error
                assert "scheduled" in res_rem.content[0].text

        # Verify items in SQLite
        events = storage.get_events("eleanor")
        assert len(events) == 1
        reminders = storage.get_reminders("eleanor")
        assert len(reminders) == 1

    finally:
        server.should_exit = True
        await server_task
        storage.close()
        if os.path.exists(path):
            os.remove(path)

"""
Client test script for CareLoop MCP Server over Streamable HTTP.

Connects to the running CareLoop MCP server using the official MCP Python SDK
streamable-http transport, discovers registered tools, and executes:
1. log_routine_event (medication)
2. log_routine_event (meal with custom timestamp)
3. check_routine_health
4. schedule_reminder
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def run_client_test(server_url: str) -> None:
    print("=" * 60)
    print(f"Connecting to CareLoop Streamable HTTP MCP Server at: {server_url}")
    print("=" * 60)

    try:
        async with streamable_http_client(server_url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # 1. Initialize session with server
                init_result = await session.initialize()
                print(f"\n[1] Connected to MCP Server: {init_result.server_info.name} (v{init_result.server_info.version})")
                print(f"    Protocol version: {init_result.protocol_version}")

                # 2. List available tools
                tools_response = await session.list_tools()
                print(f"\n[2] Discovered {len(tools_response.tools)} MCP Tools:")
                for tool in tools_response.tools:
                    print(f"    - {tool.name}: {tool.description.strip().splitlines()[0] if tool.description else ''}")

                # 3. Call tool: log_routine_event (medication)
                print("\n[3] Calling log_routine_event(person='eleanor', type='medication')...")
                res_med = await session.call_tool(
                    "log_routine_event",
                    arguments={"person": "eleanor", "type": "medication"},
                )
                print("    Response:", res_med.content[0].text if res_med.content else res_med)

                # 4. Call tool: log_routine_event (meal with explicit timestamp)
                print("\n[4] Calling log_routine_event(person='eleanor', type='meal', timestamp='2026-10-20T12:30:00Z')...")
                res_meal = await session.call_tool(
                    "log_routine_event",
                    arguments={
                        "person": "eleanor",
                        "type": "meal",
                        "timestamp": "2026-10-20T12:30:00Z",
                    },
                )
                print("    Response:", res_meal.content[0].text if res_meal.content else res_meal)

                # 5. Call tool: check_routine_health
                print("\n[5] Calling check_routine_health(person='eleanor')...")
                res_health = await session.call_tool(
                    "check_routine_health",
                    arguments={"person": "eleanor"},
                )
                print("    Response:", res_health.content[0].text if res_health.content else res_health)

                # 6. Call tool: schedule_reminder
                print("\n[6] Calling schedule_reminder(person='eleanor', text='Hydrate and take afternoon walk', time='15:00')...")
                res_rem = await session.call_tool(
                    "schedule_reminder",
                    arguments={
                        "person": "eleanor",
                        "text": "Hydrate and take afternoon walk",
                        "time": "15:00",
                    },
                )
                print("    Response:", res_rem.content[0].text if res_rem.content else res_rem)

                # 7. Call tool: respond_to_checkin ("I'm fine")
                print("\n[7] Calling respond_to_checkin(person='eleanor', response_text='I am fine, thank you!')...")
                res_checkin = await session.call_tool(
                    "respond_to_checkin",
                    arguments={
                        "person": "eleanor",
                        "response_text": "I am fine, thank you!",
                    },
                )
                print("    Response:", res_checkin.content[0].text if res_checkin.content else res_checkin)

                print("\n" + "=" * 60)
                print("✅ All MCP tools executed successfully over Streamable HTTP!")
                print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error connecting to MCP server: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Test CareLoop Streamable HTTP MCP tools")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000/mcp",
        help="Streamable HTTP MCP endpoint URL (default: http://127.0.0.1:8000/mcp)",
    )
    args = parser.parse_args()
    asyncio.run(run_client_test(args.url))


if __name__ == "__main__":
    main()

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

                # 6. Call tool: tick_escalation
                print("\n[6] Calling tick_escalation(person='eleanor')...")
                res_tick = await session.call_tool(
                    "tick_escalation",
                    arguments={"person": "eleanor"},
                )
                print("    Response:", res_tick.content[0].text if res_tick.content else res_tick)

                # 7. Call tool: confirm_ok
                print("\n[7] Calling confirm_ok(person='eleanor')...")
                res_ok = await session.call_tool(
                    "confirm_ok",
                    arguments={"person": "eleanor"},
                )
                print("    Response:", res_ok.content[0].text if res_ok.content else res_ok)

                # 8. Call tool: daily_summary
                print("\n[8] Calling daily_summary(person='eleanor', date='today')...")
                res_summary = await session.call_tool(
                    "daily_summary",
                    arguments={"person": "eleanor", "date": "today"},
                )
                print("    Response:", res_summary.content[0].text if res_summary.content else res_summary)

                # 9. Call tool: ask_memory
                print("\n[9] Calling ask_memory(person='eleanor', question='Did Eleanor take her morning medicine?')...")
                res_mem = await session.call_tool(
                    "ask_memory",
                    arguments={
                        "person": "eleanor",
                        "question": "Did Eleanor take her morning medicine?",
                    },
                )
                print("    Response:", res_mem.content[0].text if res_mem.content else res_mem)

                # 10. Call tool: notify_family
                print("\n[10] Calling notify_family(person='eleanor', severity='high', message='Routine check-in test alert')...")
                res_notify = await session.call_tool(
                    "notify_family",
                    arguments={
                        "person": "eleanor",
                        "severity": "high",
                        "message": "Routine check-in test alert dispatched via CareLoop.",
                    },
                )
                print("    Response:", res_notify.content[0].text if res_notify.content else res_notify)

                # 11. Call tool: schedule_reminder
                print("\n[11] Calling schedule_reminder(person='eleanor', text='Hydrate and take afternoon walk', time='15:00')...")
                res_rem = await session.call_tool(
                    "schedule_reminder",
                    arguments={
                        "person": "eleanor",
                        "text": "Hydrate and take afternoon walk",
                        "time": "15:00",
                    },
                )
                print("    Response:", res_rem.content[0].text if res_rem.content else res_rem)

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

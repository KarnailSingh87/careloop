"""
Main entry point for CareLoop Streamable HTTP MCP Server.

Supports FastMCP / MCPServer over streamable HTTP (MCP spec 2025-11-25+).
Includes background escalation loop for autonomous routine health monitoring.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import logging
import os
from typing import Optional, Tuple

# Support both FastMCP in mcp 1.x and renamed MCPServer in mcp 2.x
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP  # type: ignore

from starlette.applications import Starlette
from starlette.responses import JSONResponse, HTMLResponse
from starlette.routing import Route
import uvicorn

from careloop.clock import Clock, SystemClock, SimulatedClock
from careloop.engine.baseline import BaselineEngine
from careloop.engine.escalation import EscalationEngine
from careloop.engine.risk import RiskEngine
from careloop.llm.bedrock import BedrockAssistant
from careloop.notifier import get_default_notifier
from careloop.server.tools import register_tools
from careloop.storage.base import StorageBase
from careloop.storage.sqlite_store import SQLiteStorage
from careloop.storage.dynamo_store import DynamoDBStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("careloop.server")


def create_server(
    storage: Optional[StorageBase] = None,
    clock: Optional[Clock] = None,
    name: str = "CareLoop",
) -> Tuple[FastMCP, StorageBase, Clock, EscalationEngine]:
    """
    Construct the CareLoop FastMCP server with injectable storage and clock.
    """
    if storage is None:
        backend = os.getenv("STORAGE_BACKEND", "sqlite").lower()
        if backend == "dynamodb":
            table_name = os.getenv("DYNAMODB_TABLE_NAME", "CareLoopData")
            region = os.getenv("AWS_REGION", "us-east-1")
            storage = DynamoDBStorage(table_name=table_name, region_name=region)
        else:
            db_path = os.getenv("SQLITE_DB_PATH", "careloop_local.db")
            storage = SQLiteStorage(db_path=db_path)

    if clock is None:
        clock_mode = os.getenv("CLOCK_MODE", "system").lower()
        if clock_mode == "simulated":
            clock = SimulatedClock()
        else:
            clock = SystemClock()

    baseline_engine = BaselineEngine()
    risk_engine = RiskEngine()
    notifier = get_default_notifier()
    escalation_engine = EscalationEngine(
        storage=storage,
        risk_engine=risk_engine,
        baseline_engine=baseline_engine,
        notifier=notifier,
    )
    llm_assistant = BedrockAssistant()

    server = FastMCP(
        name=name,
        instructions=(
            "CareLoop MCP server for Alexa+ elder routine monitoring and safety. "
            "Logs events, checks baseline routine health, schedules reminders, "
            "answers caregiver memory questions, and dispatches family alerts when needed."
        ),
    )

    # Register all Alexa+ MCP tools
    register_tools(
        server=server,
        storage=storage,
        clock=clock,
        escalation_engine=escalation_engine,
        baseline_engine=baseline_engine,
        notifier=notifier,
        llm_assistant=llm_assistant,
    )

    return server, storage, clock, escalation_engine


def create_app(
    storage: Optional[StorageBase] = None,
    clock: Optional[Clock] = None,
    tick_interval_seconds: float = 30.0,
    enable_background_loop: bool = True,
) -> Starlette:
    """
    Build the ASGI Starlette app wrapping the MCP Streamable HTTP transport.
    Runs a periodic escalation background loop so routines are monitored autonomously.
    """
    server, storage_inst, clock_inst, escalation_inst = create_server(
        storage=storage, clock=clock
    )
    app = server.streamable_http_app()

    # Autonomous escalation background task
    async def escalation_background_loop():
        logger.info(f"Escalation autonomous background loop started (interval={tick_interval_seconds}s)")
        while True:
            try:
                await asyncio.sleep(tick_interval_seconds)
                now = clock_inst.now()
                # Run tick on monitored elders
                escalation_inst.tick("eleanor", now)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in escalation background loop: {e}")

    # Wrap Starlette lifespan context
    orig_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan_wrapper(application):
        async with orig_lifespan(application) as state:
            loop_task = None
            if enable_background_loop:
                loop_task = asyncio.create_task(escalation_background_loop())
            try:
                yield state
            finally:
                if loop_task:
                    loop_task.cancel()
                    try:
                        await loop_task
                    except asyncio.CancelledError:
                        pass

    app.router.lifespan_context = lifespan_wrapper

    # Health check endpoint for AWS ECS / ALB / local verification
    async def health_endpoint(request):
        state = storage_inst.get_escalation_state("eleanor")
        return JSONResponse({
            "status": "healthy",
            "service": "careloop",
            "version": "0.1.0",
            "clock_utc": clock_inst.now().isoformat(),
            "monitored_person": "eleanor",
            "escalation_stage": state.stage.value if state else "normal",
        })

    # Optional local simulator dashboard endpoint
    async def simulator_endpoint(request):
        sim_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "simulator", "index.html"
        )
        if os.path.exists(sim_path):
            with open(sim_path, "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())
        return HTMLResponse("<h1>CareLoop Simulator UI</h1><p>Running on /mcp</p>")

    app.routes.append(Route("/health", health_endpoint, methods=["GET"]))
    app.routes.append(Route("/simulator", simulator_endpoint, methods=["GET"]))

    return app


def main() -> None:
    """CLI launcher for CareLoop MCP server."""
    parser = argparse.ArgumentParser(description="Run CareLoop MCP Streamable HTTP server")
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"), help="Host to bind")
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", 8000)), help="Port to bind")
    parser.add_argument("--db", default=os.getenv("SQLITE_DB_PATH", "careloop_local.db"), help="SQLite DB path")
    parser.add_argument("--clock", choices=["system", "simulated"], default="system", help="Clock mode")
    parser.add_argument(
        "--tick-interval",
        type=float,
        default=float(os.getenv("ESCALATION_TICK_INTERVAL_SECONDS", 30.0)),
        help="Background escalation tick interval in seconds",
    )
    parser.add_argument(
        "--disable-background-loop",
        action="store_true",
        help="Disable autonomous background escalation loop",
    )

    args = parser.parse_args()

    clock = SimulatedClock() if args.clock == "simulated" else SystemClock()
    storage = SQLiteStorage(db_path=args.db)

    app = create_app(
        storage=storage,
        clock=clock,
        tick_interval_seconds=args.tick_interval,
        enable_background_loop=not args.disable_background_loop,
    )

    logger.info(f"Starting CareLoop MCP Server on http://{args.host}:{args.port}")
    logger.info(f"Streamable HTTP MCP endpoint: http://{args.host}:{args.port}/mcp")
    logger.info(f"Simulator Web UI: http://{args.host}:{args.port}/simulator")
    logger.info(f"Health Check: http://{args.host}:{args.port}/health")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

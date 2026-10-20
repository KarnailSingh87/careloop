"""
Main entry point for CareLoop Streamable HTTP MCP Server.

Supports FastMCP / MCPServer over streamable HTTP (MCP spec 2025-11-25+).
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import Optional

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
) -> tuple[FastMCP, StorageBase, Clock]:
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

    server = FastMCP(
        name=name,
        instructions=(
            "CareLoop MCP server for Alexa+ elder routine monitoring and safety. "
            "Logs events, checks baseline routine health, and schedules voice reminders."
        ),
    )

    # Register the required tools
    register_tools(server=server, storage=storage, clock=clock)

    return server, storage, clock


def create_app(
    storage: Optional[StorageBase] = None,
    clock: Optional[Clock] = None,
) -> Starlette:
    """
    Build the ASGI Starlette app wrapping the MCP Streamable HTTP transport.
    Adds convenient /health and /simulator endpoints alongside /mcp.
    """
    server, storage_inst, clock_inst = create_server(storage=storage, clock=clock)
    app = server.streamable_http_app()

    # Health check endpoint for AWS ECS / ALB / local verification
    async def health_endpoint(request):
        return JSONResponse({
            "status": "healthy",
            "service": "careloop",
            "version": "0.1.0",
            "clock_utc": clock_inst.now().isoformat(),
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

    args = parser.parse_args()

    clock = SimulatedClock() if args.clock == "simulated" else SystemClock()
    storage = SQLiteStorage(db_path=args.db)

    app = create_app(storage=storage, clock=clock)

    logger.info(f"Starting CareLoop MCP Server on http://{args.host}:{args.port}")
    logger.info(f"Streamable HTTP MCP endpoint: http://{args.host}:{args.port}/mcp")
    logger.info(f"Simulator Web UI: http://{args.host}:{args.port}/simulator")
    logger.info(f"Health Check: http://{args.host}:{args.port}/health")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

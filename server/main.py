"""
CareLoop MCP Server Entry Point.

Visibly imports and executes the CareLoop FastMCP Streamable HTTP server.
Can be executed directly via:
    python server/main.py
"""

from __future__ import annotations

import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Visibly import FastMCP and core server components
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP  # type: ignore

from careloop.server.main import (
    create_server,
    create_app,
    main as careloop_main,
    AlexaAuthMiddleware,
)

__all__ = [
    "FastMCP",
    "create_server",
    "create_app",
    "careloop_main",
    "AlexaAuthMiddleware",
]

if __name__ == "__main__":
    careloop_main()

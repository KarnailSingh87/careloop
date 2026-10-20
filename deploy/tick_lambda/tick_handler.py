"""
AWS Lambda tick handler invoked by EventBridge every minute.

Sends an autonomous routine tick to the CareLoop MCP server to advance the
escalation state machine, check routine windows, and dispatch alerts if needed.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    EventBridge scheduled tick invocation handler.
    Calls the CareLoop MCP server's tick_escalation tool via the REST bridge endpoint.
    """
    server_base_url = os.getenv("MCP_SERVER_URL", "").rstrip("/")
    if not server_base_url:
        logger.error("Missing MCP_SERVER_URL environment variable.")
        return {"statusCode": 500, "error": "MCP_SERVER_URL not configured"}

    target_endpoint = f"{server_base_url}/api/mcp/call"
    payload = {
        "tool": "tick_escalation",
        "arguments": {},
    }

    req_data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    auth_token = (os.getenv("ALEXA_AUTH_TOKEN") or os.getenv("MCP_AUTH_TOKEN") or "").strip()
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
        headers["x-alexa-auth-token"] = auth_token

    req = urllib.request.Request(
        target_endpoint,
        data=req_data,
        headers=headers,
        method="POST",
    )

    try:
        logger.info(f"Dispatching minute tick to CareLoop MCP server: {target_endpoint}")
        with urllib.request.urlopen(req, timeout=15) as response:
            status_code = response.getcode()
            response_body = response.read().decode("utf-8")
            result = json.loads(response_body)

            logger.info(f"CareLoop tick successful (status={status_code}): {result}")
            return {
                "statusCode": 200,
                "message": "CareLoop tick executed successfully",
                "result": result,
            }

    except urllib.error.HTTPError as e:
        error_content = e.read().decode("utf-8") if e.fp else str(e)
        logger.error(f"HTTP error triggering tick ({e.code}): {error_content}")
        return {
            "statusCode": e.code,
            "error": f"HTTPError {e.code}: {error_content}",
        }

    except Exception as e:
        logger.error(f"Unexpected error triggering tick: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "error": str(e),
        }

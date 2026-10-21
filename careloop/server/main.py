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
from datetime import datetime, timezone
import os
from typing import Optional, Tuple

# Support both FastMCP in mcp 1.x and renamed MCPServer in mcp 2.x
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP  # type: ignore

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, HTMLResponse, RedirectResponse
from starlette.routing import Route
import uvicorn
from dateutil import parser as date_parser
import time

from careloop.clock import Clock, SystemClock, SimulatedClock
from careloop.engine.baseline import BaselineEngine
from careloop.engine.escalation import EscalationEngine
from careloop.engine.risk import RiskEngine
from careloop.llm.bedrock import BedrockAssistant
from careloop.models import Event, EventType, EscalationStage, PersonProfile
from careloop.notifier import NotifierBase, get_default_notifier
from careloop.server.tools import register_tools
from careloop.storage.base import StorageBase
from careloop.storage.sqlite_store import SQLiteStorage
from careloop.storage.dynamo_store import DynamoDBStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("careloop.server")


from careloop.config import AppConfig, load_config
from careloop.server.security import (
    AlexaAuthMiddleware,
    SecurityHeadersMiddleware,
    RequestSizeLimitMiddleware,
    RateLimitMiddleware,
    install_privacy_log_filter,
)

install_privacy_log_filter()


def create_server(
    storage: Optional[StorageBase] = None,
    clock: Optional[Clock] = None,
    notifier: Optional[NotifierBase] = None,
    name: str = "CareLoop",
) -> Tuple[FastMCP, StorageBase, Clock, EscalationEngine]:
    """
    Construct the CareLoop FastMCP server with injectable storage, clock, and notifier.
    """
    if storage is None:
        backend = os.getenv("STORAGE_BACKEND", "sqlite").lower()
        if backend == "dynamodb":
            table_name = os.getenv("DYNAMODB_TABLE_NAME", "CareLoopData")
            region = os.getenv("AWS_REGION", "us-east-1")
            endpoint_url = os.getenv("DYNAMODB_ENDPOINT_URL")
            try:
                storage = DynamoDBStorage(
                    table_name=table_name,
                    region_name=region,
                    endpoint_url=endpoint_url,
                )
                storage.verify_table()
            except Exception as e:
                logger.critical(
                    f"FATAL: DynamoDB storage configured (table={table_name}, region={region}) "
                    f"but failed to verify: {e}. Production storage must not silently fall back to SQLite."
                )
                raise RuntimeError(
                    f"DynamoDB storage configured but unavailable on table '{table_name}': {e}"
                ) from e
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
    # Replay historical routines from storage so the baseline engine is pre-warmed beyond cold start
    try:
        loaded = baseline_engine.load_from_storage(storage)
        logger.info(f"Pre-warmed baseline engine with {loaded} historical routine observations.")
    except Exception as e:
        logger.warning(f"Could not pre-warm baseline engine: {e}")

    risk_engine = RiskEngine()
    if notifier is None:
        notifier = get_default_notifier()
    escalation_engine = EscalationEngine(
        storage=storage,
        risk_engine=risk_engine,
        baseline_engine=baseline_engine,
        notifier=notifier,
        gentle_timeout_seconds=60.0,
        repeat_timeout_seconds=60.0,
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
    notifier: Optional[NotifierBase] = None,
    tick_interval_seconds: float = 30.0,
    enable_background_loop: bool = True,
    auth_token: Optional[str] = None,
    config: Optional[AppConfig] = None,
) -> Starlette:
    """
    Build the ASGI Starlette app wrapping the MCP Streamable HTTP transport.
    Runs a periodic escalation background loop so routines are monitored autonomously.
    """
    if config is None:
        base_cfg = load_config()
        if auth_token is not None:
            config = AppConfig(
                env=base_cfg.env,
                auth_token=auth_token,
                scoped_tokens=base_cfg.scoped_tokens,
                jwt_secret=base_cfg.jwt_secret,
                allowed_origins=base_cfg.allowed_origins,
                max_request_body_size_bytes=base_cfg.max_request_body_size_bytes,
                rate_limit_rpm=base_cfg.rate_limit_rpm,
                notification_rate_limit_per_hour=base_cfg.notification_rate_limit_per_hour,
                event_retention_days=base_cfg.event_retention_days,
                alert_retention_days=base_cfg.alert_retention_days,
                enable_clock_endpoints=base_cfg.enable_clock_endpoints,
                enable_demo_endpoints=base_cfg.enable_demo_endpoints,
                enable_simulator=base_cfg.enable_simulator,
                allow_query_param_auth=base_cfg.allow_query_param_auth,
            )
        else:
            config = base_cfg

    server, storage_inst, clock_inst, escalation_inst = create_server(
        storage=storage, clock=clock, notifier=notifier
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
                escalation_inst.tick("dad", now)
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

    def _get_sim_state(person_id: str = "dad"):
        now = clock_inst.now()
        profile = storage_inst.get_profile(person_id)
        if not profile:
            profile = PersonProfile(
                person_id=person_id,
                display_name="Arthur Davis (Dad)" if person_id == "dad" else "Eleanor Davis (Mom)",
                timezone="America/New_York",
            )

        events = storage_inst.get_events(person_id, limit=50)
        events_today = [e for e in events if e.timestamp.date() == now.date()]

        # Evaluate risk
        risk = escalation_inst.risk_engine.evaluate_person_risk(
            person_id=person_id,
            now=now,
            baseline_engine=escalation_inst.baseline_engine,
            events_today=events_today,
        )

        esc_state = storage_inst.get_escalation_state(person_id)
        if not esc_state:
            esc_state = escalation_inst.get_or_create_state(person_id, now)

        alerts = storage_inst.get_alerts(person_id, active_only=False)
        profiles = storage_inst.list_profiles()

        return {
            "clock": {
                "utc": now.isoformat(),
                "time_str": now.strftime("%H:%M:%S UTC"),
                "date_str": now.strftime("%Y-%m-%d"),
                "is_simulated": isinstance(clock_inst, SimulatedClock),
            },
            "person": {
                "id": person_id,
                "display_name": profile.display_name if profile else person_id.capitalize(),
                "timezone": profile.timezone if profile else "America/New_York",
                "emergency_contacts": [
                    {"name": c.name, "relationship": c.relationship, "phone": c.phone}
                    for c in (profile.emergency_contacts if profile else [])
                ],
            },
            "escalation": {
                "stage": esc_state.stage.value,
                "risk_score": esc_state.risk_score,
                "reasons": esc_state.reasons,
                "last_updated": esc_state.last_updated.isoformat(),
            },
            "risk": {
                "score": risk.score,
                "level": risk.level,
                "reasons": risk.reasons,
                "anomalies": risk.anomalies,
            },
            "events_today": [
                {
                    "event_id": e.event_id,
                    "type": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                    "time": e.timestamp.strftime("%H:%M"),
                    "timestamp": e.timestamp.isoformat(),
                    "metadata": e.metadata,
                }
                for e in sorted(events_today, key=lambda x: x.timestamp, reverse=True)
            ],
            "alerts": [
                {
                    "alert_id": a.alert_id,
                    "level": a.level.value if hasattr(a.level, "value") else str(a.level),
                    "title": a.title,
                    "reasons": a.reasons,
                    "status": a.status,
                    "created_at": a.created_at.isoformat(),
                    "time_str": a.created_at.strftime("%H:%M UTC"),
                }
                for a in alerts
            ],
            "available_profiles": [
                {"id": p.person_id, "name": p.display_name} for p in profiles
            ],
        }

    # Health check endpoint for AWS ECS / ALB / local verification
    async def health_endpoint(request):
        state = storage_inst.get_escalation_state("dad") or storage_inst.get_escalation_state("eleanor")
        return JSONResponse({
            "status": "healthy",
            "service": "careloop",
            "version": "0.1.0",
            "clock_utc": clock_inst.now().isoformat(),
            "monitored_person": "dad",
            "escalation_stage": state.stage.value if state else "normal",
        })

    # Simulator dashboard endpoint
    async def simulator_endpoint(request):
        sim_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "simulator", "index.html"
        )
        if os.path.exists(sim_path):
            with open(sim_path, "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())
        return HTMLResponse("<h1>CareLoop Simulator UI</h1><p>Running on /mcp</p>")

    async def root_endpoint(request):
        return RedirectResponse(url="/simulator")

    # API endpoints for Simulator UI
    async def api_state_endpoint(request):
        person_id = request.query_params.get("person", "dad").strip().lower()
        return JSONResponse(_get_sim_state(person_id))

    async def api_clock_advance(request):
        if not config.enable_clock_endpoints:
            return JSONResponse(
                {"error": "Forbidden: Clock manipulation is disabled in this environment."},
                status_code=403,
            )
        try:
            body = await request.json()
        except Exception:
            body = {}
        minutes = int(body.get("minutes", 60))
        person_id = body.get("person", "dad").strip().lower()

        if isinstance(clock_inst, SimulatedClock):
            clock_inst.advance(minutes * 60)
            now = clock_inst.now()
            escalation_inst.tick(person_id, now)

        return JSONResponse(_get_sim_state(person_id))

    async def api_clock_set(request):
        if not config.enable_clock_endpoints:
            return JSONResponse(
                {"error": "Forbidden: Clock manipulation is disabled in this environment."},
                status_code=403,
            )
        try:
            body = await request.json()
        except Exception:
            body = {}
        time_val = body.get("time", "14:00")
        person_id = body.get("person", "dad").strip().lower()

        if isinstance(clock_inst, SimulatedClock):
            now = clock_inst.now()
            if time_val in ("2pm", "14:00", "today_14:00"):
                target = now.replace(hour=14, minute=0, second=0, microsecond=0)
            else:
                try:
                    parsed = date_parser.parse(time_val)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    target = parsed
                except Exception:
                    target = now.replace(hour=14, minute=0, second=0, microsecond=0)
            clock_inst.set_time(target)
            escalation_inst.tick(person_id, target)

        return JSONResponse(_get_sim_state(person_id))

    async def api_clock_reset(request):
        if not config.enable_clock_endpoints:
            return JSONResponse(
                {"error": "Forbidden: Clock manipulation is disabled in this environment."},
                status_code=403,
            )
        try:
            body = await request.json()
        except Exception:
            body = {}
        person_id = body.get("person", "dad").strip().lower()

        if isinstance(clock_inst, SimulatedClock):
            if hasattr(storage_inst, "clear_demo_data"):
                storage_inst.clear_demo_data(person_id)
                storage_inst.clear_demo_data("eleanor")
            base_reset = datetime(2026, 10, 20, 8, 15, 0, tzinfo=timezone.utc)
            clock_inst.set_time(base_reset)
            escalation_inst.reset_to_normal(person_id, base_reset, reason="Simulation reset to 08:15 AM")
            escalation_inst.reset_to_normal("eleanor", base_reset, reason="Simulation reset to 08:15 AM")

        return JSONResponse(_get_sim_state(person_id))

    async def api_mcp_call(request):
        start_time = time.time()
        try:
            body = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON body: {e}"}, status_code=400)

        tool_name = body.get("tool")
        arguments = body.get("arguments", {})

        if not tool_name:
            return JSONResponse({"error": "Missing 'tool' in request body"}, status_code=400)

        try:
            call_res = await server.call_tool(tool_name, arguments)
            duration_ms = round((time.time() - start_time) * 1000, 2)

            res_data = None
            if hasattr(call_res, "structured_content") and call_res.structured_content:
                res_data = call_res.structured_content.get("result", call_res.structured_content)
            elif hasattr(call_res, "content") and call_res.content:
                try:
                    res_data = json.loads(call_res.content[0].text)
                except Exception:
                    res_data = call_res.content[0].text

            return JSONResponse({
                "jsonrpc": "2.0",
                "id": body.get("id", int(time.time() * 1000)),
                "tool": tool_name,
                "arguments": arguments,
                "result": res_data,
                "raw_text": call_res.content[0].text if hasattr(call_res, "content") and call_res.content else "",
                "is_error": getattr(call_res, "is_error", False),
                "duration_ms": duration_ms,
                "protocol_version": "2025-11-25",
            })
        except Exception as e:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.error(f"Error executing MCP tool '{tool_name}': {e}")
            if hasattr(e, "__class__") and e.__class__.__name__ == "ToolError":
                safe_msg = str(e)
            elif config.is_production():
                safe_msg = "An internal server error occurred while executing the tool."
            else:
                safe_msg = str(e)

            return JSONResponse({
                "jsonrpc": "2.0",
                "id": body.get("id", int(time.time() * 1000)),
                "tool": tool_name,
                "arguments": arguments,
                "error": {"code": -32603, "message": safe_msg},
                "is_error": True,
                "duration_ms": duration_ms,
                "protocol_version": "2025-11-25",
            }, status_code=500)

    async def api_mcp_tools(request):
        tool_objs = await server.list_tools()
        tools_list = []
        for t in tool_objs:
            tools_list.append({
                "name": t.name,
                "description": t.description,
                "parameters": getattr(t, "parameters", {}),
            })
        return JSONResponse({"tools": tools_list})

    async def api_demo_skips_lunch_setup(request):
        if not config.enable_demo_endpoints:
            return JSONResponse(
                {"error": "Forbidden: Demo endpoints are disabled in this environment."},
                status_code=403,
            )
        person_id = "dad"
        if hasattr(storage_inst, "clear_demo_data"):
            storage_inst.clear_demo_data(person_id)

        if isinstance(clock_inst, SimulatedClock):
            clock_inst.set_time(datetime(2026, 10, 20, 8, 30, 0, tzinfo=timezone.utc))

        # Seed morning routine today
        storage_inst.save_event(
            Event(
                person_id=person_id,
                event_type=EventType.MOVEMENT,
                timestamp=datetime(2026, 10, 20, 7, 30, 0, tzinfo=timezone.utc),
                metadata={"source": "simulator_demo", "room": "bedroom"},
            )
        )
        storage_inst.save_event(
            Event(
                person_id=person_id,
                event_type=EventType.PILL,
                timestamp=datetime(2026, 10, 20, 8, 15, 0, tzinfo=timezone.utc),
                metadata={"medication": "blood_pressure_lisinopril", "source": "simulator_demo"},
            )
        )
        escalation_inst.reset_to_normal(person_id, clock_inst.now(), reason="Dad skips lunch scenario setup")

        return JSONResponse(_get_sim_state(person_id))

    async def api_demo_reset(request):
        if not config.enable_demo_endpoints:
            return JSONResponse(
                {"error": "Forbidden: Demo endpoints are disabled in this environment."},
                status_code=403,
            )
        try:
            body = await request.json()
        except Exception:
            body = {}
        person_id = body.get("person", "dad").strip().lower()

        if not isinstance(clock_inst, SimulatedClock):
            return JSONResponse(
                {"error": "Demo reset is disabled in production system mode."},
                status_code=403,
            )

        if hasattr(storage_inst, "clear_demo_data"):
            storage_inst.clear_demo_data(person_id)

        base_reset = datetime(2026, 10, 20, 8, 15, 0, tzinfo=timezone.utc)
        clock_inst.set_time(base_reset)
        escalation_inst.reset_to_normal(person_id, base_reset, reason="Simulation demo reset")
        return JSONResponse(_get_sim_state(person_id))

    async def oauth_protected_resource_metadata(request: Request) -> JSONResponse:
        """
        RFC 9728 OAuth 2.0 Protected Resource Metadata endpoint.
        Discovered by Alexa+ MCP Toolkit to determine authorization server boundaries.
        """
        host = request.headers.get("host", "127.0.0.1:8000")
        proto = "https" if request.url.is_secure or "https" in request.headers.get("x-forwarded-proto", "") else "http"
        base_url = f"{proto}://{host}"
        return JSONResponse({
            "resource": base_url,
            "authorization_servers": [f"{base_url}/oauth"],
            "scopes_supported": ["careloop:elder:read", "careloop:elder:write", "careloop:mcp"],
            "bearer_methods_supported": ["header"],
            "resource_documentation": "https://github.com/KarnailSingh87/careloop",
        })

    async def oauth_authorization_server_metadata(request: Request) -> JSONResponse:
        """
        RFC 8414 OAuth 2.0 Authorization Server Metadata endpoint.
        Declares OAuth 2.1 PKCE (S256) support for Alexa+ Tier 2 account linking.
        """
        host = request.headers.get("host", "127.0.0.1:8000")
        proto = "https" if request.url.is_secure or "https" in request.headers.get("x-forwarded-proto", "") else "http"
        base_url = f"{proto}://{host}"
        return JSONResponse({
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/oauth/authorize",
            "token_endpoint": f"{base_url}/oauth/token",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "client_credentials"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
            "scopes_supported": ["careloop:elder:read", "careloop:elder:write", "careloop:mcp"],
        })

    app.routes.append(Route("/", root_endpoint, methods=["GET"]))
    app.routes.append(Route("/health", health_endpoint, methods=["GET"]))
    app.routes.append(Route("/simulator", simulator_endpoint, methods=["GET"]))
    app.routes.append(Route("/.well-known/oauth-protected-resource", oauth_protected_resource_metadata, methods=["GET"]))
    app.routes.append(Route("/.well-known/oauth-authorization-server", oauth_authorization_server_metadata, methods=["GET"]))
    app.routes.append(Route("/api/state", api_state_endpoint, methods=["GET"]))
    app.routes.append(Route("/api/clock/advance", api_clock_advance, methods=["POST"]))
    app.routes.append(Route("/api/clock/set", api_clock_set, methods=["POST"]))
    app.routes.append(Route("/api/clock/reset", api_clock_reset, methods=["POST"]))
    app.routes.append(Route("/api/mcp/call", api_mcp_call, methods=["POST"]))
    app.routes.append(Route("/api/mcp/tools", api_mcp_tools, methods=["GET"]))
    app.routes.append(Route("/api/demo/skips-lunch/setup", api_demo_skips_lunch_setup, methods=["POST"]))
    app.routes.append(Route("/api/demo/reset", api_demo_reset, methods=["POST"]))

    # Alias /v1/mcp to the same endpoint as /mcp for Alexa+ versioned route compatibility
    mcp_route = next((r for r in app.routes if getattr(r, "path", None) == "/mcp"), None)
    if mcp_route and hasattr(mcp_route, "endpoint"):
        app.routes.append(Route("/v1/mcp", mcp_route.endpoint))

    # Add Middlewares in order:
    # 1. Alexa+ authentication & SecurityContext middleware (innermost)
    app.add_middleware(AlexaAuthMiddleware, config=config, auth_token=auth_token)

    # 2. CORS middleware (safe origin policy)
    if config.is_production():
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.allowed_origins,
            allow_credentials=bool(config.allowed_origins),
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Mcp-Session-Id", "x-alexa-auth-token", "x-api-key"],
            expose_headers=["Mcp-Session-Id", "Content-Type", "WWW-Authenticate"],
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["Mcp-Session-Id", "Content-Type", "WWW-Authenticate"],
        )

    # 3. Request body size limit middleware (defense against memory exhaustion DoS)
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_size_bytes=config.max_request_body_size_bytes,
    )

    # 4. Sliding-window rate limit middleware (defense against abuse / rapid bursts)
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=config.rate_limit_rpm,
    )

    # 5. Strict security headers middleware (outermost)
    app.add_middleware(
        SecurityHeadersMiddleware,
        is_production=config.is_production(),
    )

    return app


def main() -> None:
    """CLI launcher for CareLoop MCP server."""
    parser = argparse.ArgumentParser(description="Run CareLoop MCP Streamable HTTP server")
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"), help="Host to bind")
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", 8000)), help="Port to bind")
    parser.add_argument("--db", default=os.getenv("SQLITE_DB_PATH", "careloop_local.db"), help="SQLite DB path")
    parser.add_argument("--clock", choices=["system", "simulated"], default="system", help="Clock mode")
    parser.add_argument(
        "--storage",
        choices=["sqlite", "dynamodb"],
        default=os.getenv("STORAGE_BACKEND", "sqlite").lower(),
        help="Storage backend ('sqlite' or 'dynamodb')",
    )
    parser.add_argument(
        "--dynamo-table",
        default=os.getenv("DYNAMODB_TABLE_NAME", "CareLoopData"),
        help="DynamoDB table name when using dynamodb storage",
    )
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
    parser.add_argument(
        "--env",
        choices=["development", "test", "production"],
        default=os.getenv("CARELOOP_ENV", "development").lower(),
        help="Deployment environment ('development', 'test', 'production')",
    )
    parser.add_argument(
        "--auth-token",
        default=os.getenv("ALEXA_AUTH_TOKEN"),
        help="Alexa+ Bearer authentication token for securing the MCP endpoint",
    )

    args = parser.parse_args()

    # Centralized configuration with production fail-closed validation
    env_override = dict(os.environ)
    env_override["CARELOOP_ENV"] = args.env
    if args.auth_token:
        env_override["ALEXA_AUTH_TOKEN"] = args.auth_token

    config = load_config(env_dict=env_override)

    clock = SimulatedClock() if args.clock == "simulated" else SystemClock()
    if args.storage == "dynamodb":
        region = os.getenv("AWS_REGION", "us-east-1")
        storage = DynamoDBStorage(table_name=args.dynamo_table, region_name=region)
        logger.info(f"Initialized DynamoDBStorage (table={args.dynamo_table}, region={region})")
    else:
        storage = SQLiteStorage(db_path=args.db)
        logger.info(f"Initialized SQLiteStorage (db={args.db})")

    app = create_app(
        storage=storage,
        clock=clock,
        tick_interval_seconds=args.tick_interval,
        enable_background_loop=not args.disable_background_loop,
        auth_token=args.auth_token,
        config=config,
    )

    logger.info(f"Starting CareLoop MCP Server on http://{args.host}:{args.port} [env={config.env}]")
    logger.info(f"Streamable HTTP MCP endpoint: http://{args.host}:{args.port}/mcp")
    if config.enable_simulator:
        logger.info(f"Simulator Web UI: http://{args.host}:{args.port}/simulator")
    logger.info(f"Health Check: http://{args.host}:{args.port}/health")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

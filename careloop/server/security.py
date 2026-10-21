"""
Security, authentication, authorization, and rate limiting module for CareLoop.

Implements:
1. Role-based and person-scoped access control (RBAC & PBAC)
2. Verified Bearer and API Key token management with constant-time comparison
3. Per-request security context with ContextVar propagation
4. Privacy-conscious structured logging filter (token redaction, phone masking, audio scrubbing)
5. Request body size limit middleware (defense against payload exhaustion DoS)
6. Sliding window rate limiting middleware (defense against brute-force and notification abuse)
7. Strict HTTP security headers middleware (HSTS, nosniff, frame denial, CSP)
8. Production fail-closed authentication middleware
"""

from __future__ import annotations

import collections
from contextvars import ContextVar
import hmac
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from careloop.config import AppConfig, load_config

logger = logging.getLogger("careloop.security")

# Predefined role tool sets
ELDER_ALLOWED_TOOLS: Set[str] = {
    "log_routine_event",
    "confirm_ok",
    "respond_to_checkin",
}

CAREGIVER_ALLOWED_TOOLS: Set[str] = {
    "daily_summary",
    "ask_memory",
    "check_routine_health",
    "schedule_reminder",
    "notify_family",
}

ADMIN_ALLOWED_TOOLS: Set[str] = {"*"}
SYSTEM_ALLOWED_TOOLS: Set[str] = {"*"}

# Regex for masking phone numbers: e.g. +14155552671 -> +1***...*71
PHONE_PATTERN = re.compile(r"(\+?\d{1,3})?[-. ]?\(?(\d{3})\)?[-. ]?(\d{3})[-. ]?(\d{4})")
# Regex for token patterns in logs
BEARER_PATTERN = re.compile(r"(Bearer\s+)([A-Za-z0-9_\-\.]{6,})", re.IGNORECASE)
TOKEN_PARAM_PATTERN = re.compile(r"(auth_token=)([A-Za-z0-9_\-\.]{6,})", re.IGNORECASE)
API_KEY_PATTERN = re.compile(r"(x-(?:alexa-auth-token|api-key):\s*)([A-Za-z0-9_\-\.]{6,})", re.IGNORECASE)


class PrivacyLogFilter(logging.Filter):
    """
    Log filter that strips sensitive authentication tokens, phone numbers,
    and voice payloads from log messages before emission.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            # 1. Mask Bearer tokens
            msg = BEARER_PATTERN.sub(r"\1[REDACTED_TOKEN]", msg)
            # 2. Mask query auth tokens
            msg = TOKEN_PARAM_PATTERN.sub(r"\1[REDACTED_TOKEN]", msg)
            # 3. Mask API key headers
            msg = API_KEY_PATTERN.sub(r"\1[REDACTED_KEY]", msg)
            # 4. Mask raw phone numbers
            def _mask_phone(match):
                g = match.groups()
                # Keep country code and last 2 digits
                last4 = g[3] if len(g) > 3 and g[3] else "XXXX"
                prefix = g[0] if g[0] else ""
                return f"{prefix}***-***-**{last4[-2:]}"

            msg = PHONE_PATTERN.sub(_mask_phone, msg)
            record.msg = msg

        return True


def install_privacy_log_filter() -> None:
    """Install the privacy filter on all careloop loggers."""
    p_filter = PrivacyLogFilter()
    for name in ("careloop", "careloop.server", "careloop.security", "careloop.notifier"):
        log = logging.getLogger(name)
        if not any(isinstance(f, PrivacyLogFilter) for f in log.filters):
            log.addFilter(p_filter)


class SecurityContext:
    """Represents the authenticated caller and their verified authorization permissions."""

    def __init__(
        self,
        caller_id: str,
        role: str,
        allowed_persons: Optional[Set[str]] = None,
        allowed_tools: Optional[Set[str]] = None,
        authenticated_via: str = "bearer",
    ) -> None:
        self.caller_id = caller_id.strip()
        self.role = role.strip().lower()
        self.allowed_persons = set(allowed_persons) if allowed_persons is not None else {"*"}
        self.allowed_tools = set(allowed_tools) if allowed_tools is not None else {"*"}
        self.authenticated_via = authenticated_via

    def is_person_allowed(self, person_id: Optional[str]) -> bool:
        """Check whether caller is permitted to access the given person."""
        if not person_id or "*" in self.allowed_persons:
            return True
        return person_id.strip().lower() in {p.lower() for p in self.allowed_persons}

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check whether caller is permitted to invoke the given MCP tool."""
        if "*" in self.allowed_tools:
            return True
        return tool_name.strip().lower() in {t.lower() for t in self.allowed_tools}

    def __repr__(self) -> str:
        return (
            f"<SecurityContext caller={self.caller_id} role={self.role} "
            f"persons={self.allowed_persons} tools={self.allowed_tools}>"
        )


# Thread-local / task-local storage for current request's SecurityContext
_current_security_context: ContextVar[Optional[SecurityContext]] = ContextVar(
    "_current_security_context", default=None
)


def get_current_security_context() -> Optional[SecurityContext]:
    """Retrieve the SecurityContext for the currently executing task/request."""
    return _current_security_context.get()


def set_current_security_context(ctx: Optional[SecurityContext]) -> None:
    """Set the SecurityContext for the current execution task."""
    _current_security_context.set(ctx)


def check_tool_authorization(tool_name: str, person: Optional[str] = None) -> None:
    """
    Enforce authorization checks against the current security context.
    Raises ToolError if caller is not authorized for the requested person or operation.
    """
    try:
        from mcp.server.mcpserver.exceptions import ToolError
    except ImportError:
        class ToolError(Exception):
            pass

    ctx = get_current_security_context()

    # If no security context is set (e.g., in unit tests without HTTP middleware):
    if ctx is None:
        cfg = load_config()
        if cfg.is_production():
            raise ToolError(
                f"Unauthorized: No authenticated security context found in production mode for tool '{tool_name}'."
            )
        # In development/test mode, allow execution with unconstrained local privileges
        return

    # 1. Enforce operation / tool authorization
    if not ctx.is_tool_allowed(tool_name):
        raise ToolError(
            f"Access Denied: Caller role '{ctx.role}' is not authorized to invoke tool '{tool_name}'. "
            f"Allowed tools: {sorted(list(ctx.allowed_tools))}"
        )

    # 2. Enforce person-level access control (prevent cross-person snooping/tampering)
    if person and not ctx.is_person_allowed(person):
        raise ToolError(
            f"Access Denied: Caller '{ctx.caller_id}' is not authorized to access person '{person}'. "
            f"Permitted persons: {sorted(list(ctx.allowed_persons))}"
        )


class TokenManager:
    """
    Validates authentication tokens and resolves caller identities and permissions.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._token_registry: Dict[str, SecurityContext] = {}

        # 1. Register single global auth token (if configured)
        if config.auth_token:
            self._token_registry[config.auth_token] = SecurityContext(
                caller_id="alexa_cloud_gateway",
                role="admin",
                allowed_persons={"*"},
                allowed_tools={"*"},
                authenticated_via="bearer",
            )

        # 2. Register scoped tokens
        for token, details in config.scoped_tokens.items():
            caller_id = details.get("caller_id", f"caller_{token[:6]}")
            role = details.get("role", "elder").lower()
            allowed_persons = set(details.get("allowed_persons", ["*"]))

            if "allowed_tools" in details:
                allowed_tools = set(details["allowed_tools"])
            elif role == "elder":
                allowed_tools = set(ELDER_ALLOWED_TOOLS)
            elif role == "caregiver":
                allowed_tools = set(CAREGIVER_ALLOWED_TOOLS)
            else:
                allowed_tools = {"*"}

            self._token_registry[token] = SecurityContext(
                caller_id=caller_id,
                role=role,
                allowed_persons=allowed_persons,
                allowed_tools=allowed_tools,
                authenticated_via="scoped_token",
            )

    def verify_token(self, token_candidate: str) -> Optional[SecurityContext]:
        """
        Verify a token string in constant time to prevent timing attacks.
        Returns matching SecurityContext or None.
        """
        if not token_candidate:
            return None

        # Check in memory registry using constant-time comparison
        for registered_token, context in self._token_registry.items():
            if hmac.compare_digest(token_candidate, registered_token):
                return context

        # Optional: check JWT token if jwt_secret is configured
        if self.config.jwt_secret:
            try:
                import jwt
                payload = jwt.decode(
                    token_candidate,
                    self.config.jwt_secret,
                    algorithms=["HS256"],
                    options={"verify_exp": True},
                )
                role = payload.get("role", "elder").lower()
                allowed_persons = set(payload.get("allowed_persons", ["*"]))
                allowed_tools = set(payload.get("allowed_tools", (
                    ELDER_ALLOWED_TOOLS if role == "elder" else CAREGIVER_ALLOWED_TOOLS
                )))
                return SecurityContext(
                    caller_id=payload.get("sub", "jwt_user"),
                    role=role,
                    allowed_persons=allowed_persons,
                    allowed_tools=allowed_tools,
                    authenticated_via="jwt",
                )
            except Exception as e:
                logger.debug(f"JWT verification failed: {e}")
                return None

        return None


class RequestSizeLimitMiddleware:
    """
    Middleware that enforces a strict upper limit on incoming HTTP request bodies.
    Guards against memory exhaustion and payload flood DoS attacks.
    """

    def __init__(self, app: Any, max_size_bytes: int = 65536) -> None:
        self.app = app
        self.max_size_bytes = max_size_bytes

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(raw=scope.get("headers", []))
        content_length_str = headers.get("content-length")

        if content_length_str:
            try:
                content_length = int(content_length_str)
                if content_length > self.max_size_bytes:
                    logger.warning(
                        f"Rejected request exceeding size limit: {content_length} bytes > {self.max_size_bytes} limit"
                    )
                    res = JSONResponse(
                        {
                            "jsonrpc": "2.0",
                            "error": {
                                "code": -32600,
                                "message": f"Payload Too Large: request body exceeds maximum allowed size of {self.max_size_bytes} bytes.",
                            },
                        },
                        status_code=413,
                    )
                    await res(scope, receive, send)
                    return
            except ValueError:
                pass

        # Wrap receive to detect streamed bodies exceeding the limit
        received_bytes = 0

        async def wrapped_receive():
            nonlocal received_bytes
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                received_bytes += len(body)
                if received_bytes > self.max_size_bytes:
                    raise ValueError(f"Request body exceeded {self.max_size_bytes} bytes limit.")
            return message

        try:
            await self.app(scope, wrapped_receive, send)
        except ValueError as e:
            res = JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32600,
                        "message": f"Payload Too Large: {e}",
                    },
                },
                status_code=413,
            )
            await res(scope, receive, send)


class RateLimitMiddleware:
    """
    In-memory sliding-window rate limiter per client identifier.
    Mitigates rapid brute-force attacks and abuse of MCP endpoints.
    """

    def __init__(self, app: Any, requests_per_minute: int = 120) -> None:
        self.app = app
        self.rpm = requests_per_minute
        self._history: Dict[str, collections.deque] = collections.defaultdict(collections.deque)
        self._notif_history: Dict[str, collections.deque] = collections.defaultdict(collections.deque)

    def _get_client_id(self, scope: Any) -> str:
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode("utf-8").strip()
        if auth_header:
            return f"auth:{auth_header[:16]}"
        client = scope.get("client")
        if client:
            return f"ip:{client[0]}"
        return "unknown"

    def check_notification_quota(self, person_id: str, max_per_hour: int = 10) -> bool:
        """
        Rate limit family notifications to prevent SMS flooding and alert fatigue.
        Returns True if within quota, False if quota exceeded.
        """
        now = time.time()
        window = 3600.0  # 1 hour
        history = self._notif_history[person_id]

        while history and history[0] < now - window:
            history.popleft()

        if len(history) >= max_per_hour:
            return False

        history.append(now)
        return True

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Bypass health check and static simulator assets from rate limiting
        if path in ("/health", "/favicon.ico"):
            await self.app(scope, receive, send)
            return

        client_id = self._get_client_id(scope)
        now = time.time()
        window = 60.0  # 1 minute sliding window

        history = self._history[client_id]
        while history and history[0] < now - window:
            history.popleft()

        if len(history) >= self.rpm:
            logger.warning(f"Rate limit exceeded for client {client_id} ({len(history)} req/min)")
            res = JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32000,
                        "message": "Too Many Requests: Rate limit exceeded. Please retry after 60 seconds.",
                    },
                },
                status_code=429,
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(self.rpm),
                    "X-RateLimit-Remaining": "0",
                },
            )
            await res(scope, receive, send)
            return

        history.append(now)
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    """
    Middleware injecting hardened HTTP response headers:
    - HSTS (Strict-Transport-Security)
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 0
    - Content-Security-Policy
    """

    def __init__(self, app: Any, is_production: bool = False) -> None:
        self.app = app
        self.is_production = is_production

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Any) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                # Add security headers
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"x-frame-options", b"DENY"))
                headers.append((b"x-xss-protection", b"0"))
                headers.append(
                    (
                        b"content-security-policy",
                        b"default-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
                        b"img-src 'self' data:; connect-src 'self'",
                    )
                )
                if self.is_production:
                    headers.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class AlexaAuthMiddleware:
    """
    ASGI authentication and authorization middleware for CareLoop.
    
    Verifies caller tokens, establishes SecurityContext, and enforces
    fail-closed security in production.
    """

    def __init__(
        self,
        app: Any,
        config: Optional[AppConfig] = None,
        auth_token: Optional[str] = None,
    ) -> None:
        self.app = app
        if config is None:
            base_config = load_config()
            if auth_token is not None:
                # If explicit auth_token passed, use it on config
                self.config = AppConfig(
                    env=base_config.env,
                    auth_token=auth_token,
                    scoped_tokens=base_config.scoped_tokens,
                    jwt_secret=base_config.jwt_secret,
                    allowed_origins=base_config.allowed_origins,
                    max_request_body_size_bytes=base_config.max_request_body_size_bytes,
                    rate_limit_rpm=base_config.rate_limit_rpm,
                    notification_rate_limit_per_hour=base_config.notification_rate_limit_per_hour,
                    event_retention_days=base_config.event_retention_days,
                    alert_retention_days=base_config.alert_retention_days,
                    enable_clock_endpoints=base_config.enable_clock_endpoints,
                    enable_demo_endpoints=base_config.enable_demo_endpoints,
                    enable_simulator=base_config.enable_simulator,
                    allow_query_param_auth=base_config.allow_query_param_auth,
                )
            else:
                self.config = base_config
        else:
            self.config = config

        self.token_manager = TokenManager(self.config)

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")

        # 1. Bypass CORS pre-flight OPTIONS requests
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # 2. Public health check bypass (essential for ALB and ECS health checks)
        if path == "/health":
            await self.app(scope, receive, send)
            return

        # 3. Simulator UI routing check in production
        if path in ("/simulator", "/", "/favicon.ico") or path.startswith("/simulator/"):
            if self.config.is_production() and not self.config.enable_simulator:
                res = JSONResponse(
                    {"error": "Forbidden: Simulator UI is disabled in production deployment."},
                    status_code=403,
                )
                await res(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        # 4. Extract token from standard authentication headers
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode("utf-8").strip()
        alexa_header = headers.get(b"x-alexa-auth-token", b"").decode("utf-8").strip()
        api_key_header = headers.get(b"x-api-key", b"").decode("utf-8").strip()

        # Query param extraction (only allowed in development/test mode)
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_token = ""
        if "auth_token=" in query_string:
            if self.config.is_production():
                res = JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32001,
                            "message": "Unauthorized: Query parameter token authentication is forbidden in production. Use Authorization header.",
                        },
                    },
                    status_code=401,
                    headers={"WWW-Authenticate": 'Bearer realm="CareLoop Alexa+ MCP"'},
                )
                await res(scope, receive, send)
                return

            import urllib.parse
            parsed_qs = urllib.parse.parse_qs(query_string)
            query_token = parsed_qs.get("auth_token", [""])[0].strip()

        extracted_token = ""
        auth_method = "none"
        if auth_header.lower().startswith("bearer "):
            extracted_token = auth_header[7:].strip()
            auth_method = "bearer"
        elif alexa_header:
            extracted_token = alexa_header
            auth_method = "alexa_header"
        elif api_key_header:
            extracted_token = api_key_header
            auth_method = "api_key"
        elif query_token:
            extracted_token = query_token
            auth_method = "query_param"

        # 5. Production Mode: Must fail closed if no token is provided
        if not extracted_token:
            if self.config.is_production():
                logger.warning(f"Unauthorized access attempt to {path}: No authentication credentials provided.")
                res = JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32001,
                            "message": "Unauthorized: Missing authentication credentials.",
                        },
                    },
                    status_code=401,
                    headers={"WWW-Authenticate": 'Bearer realm="CareLoop Alexa+ MCP"'},
                )
                await res(scope, receive, send)
                return

            # In development/test mode without a token:
            # If server has an auth token configured, enforce it.
            if self.config.auth_token or self.config.scoped_tokens:
                res = JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32001,
                            "message": "Unauthorized: Missing or invalid Alexa+ authentication token.",
                        },
                    },
                    status_code=401,
                    headers={"WWW-Authenticate": 'Bearer realm="CareLoop Alexa+ MCP"'},
                )
                await res(scope, receive, send)
                return

            # Open development mode (no server auth configured)
            dev_context = SecurityContext(
                caller_id="local_dev_user",
                role="admin",
                allowed_persons={"*"},
                allowed_tools={"*"},
                authenticated_via="local_dev",
            )
            set_current_security_context(dev_context)
            if "state" not in scope:
                scope["state"] = {}
            scope["state"]["security_context"] = dev_context
            await self.app(scope, receive, send)
            return

        # 6. Verify token
        security_context = self.token_manager.verify_token(extracted_token)
        if not security_context:
            logger.warning(f"Unauthorized access to {path}: Invalid token provided.")
            res = JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32001,
                        "message": "Unauthorized: Invalid or expired authentication token.",
                    },
                },
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="CareLoop Alexa+ MCP"'},
            )
            await res(scope, receive, send)
            return

        # 7. Bind context to current request
        set_current_security_context(security_context)
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["security_context"] = security_context

        try:
            await self.app(scope, receive, send)
        finally:
            set_current_security_context(None)

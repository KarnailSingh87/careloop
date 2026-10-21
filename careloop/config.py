"""
Configuration management and secure secrets loading for CareLoop.

Supports:
- Environment detection: 'development', 'test', 'production'
- Secure secret loading from AWS Secrets Manager or environment variables
- Strict fail-closed validation for production deployments
- Configuration of rate limits, request limits, CORS, and data retention policies
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("careloop.config")

# Insecure default tokens that must NEVER be permitted in production
INSECURE_DEFAULT_TOKENS: Set[str] = {
    "",
    "default",
    "test",
    "admin",
    "changeme",
    "secret",
    "12345",
    "password",
    "test-secret-alexa-token-12345",
}


class SecurityConfigurationError(Exception):
    """Raised when an insecure configuration is detected in production mode."""
    pass


class AppConfig:
    """Centralized, immutable configuration object for CareLoop."""

    def __init__(
        self,
        env: str = "development",
        auth_token: Optional[str] = None,
        scoped_tokens: Optional[Dict[str, Dict[str, Any]]] = None,
        jwt_secret: Optional[str] = None,
        allowed_origins: Optional[List[str]] = None,
        max_request_body_size_bytes: int = 65536,  # 64 KB
        rate_limit_rpm: int = 120,
        notification_rate_limit_per_hour: int = 10,
        event_retention_days: int = 90,
        alert_retention_days: int = 180,
        enable_clock_endpoints: Optional[bool] = None,
        enable_demo_endpoints: Optional[bool] = None,
        enable_simulator: Optional[bool] = None,
        allow_query_param_auth: Optional[bool] = None,
    ) -> None:
        self.env = env.strip().lower()
        if self.env not in ("development", "test", "production"):
            self.env = "development"

        self.auth_token = auth_token.strip() if auth_token else None
        self.scoped_tokens = scoped_tokens or {}
        self.jwt_secret = jwt_secret.strip() if jwt_secret else None
        self.allowed_origins = allowed_origins or (
            ["*"] if self.env != "production" else []
        )
        self.max_request_body_size_bytes = max(1024, max_request_body_size_bytes)
        self.rate_limit_rpm = max(1, rate_limit_rpm)
        self.notification_rate_limit_per_hour = max(1, notification_rate_limit_per_hour)
        self.event_retention_days = max(1, event_retention_days)
        self.alert_retention_days = max(1, alert_retention_days)

        # Environment-dependent feature toggles (safe defaults)
        if self.env == "production":
            self.enable_clock_endpoints = (
                enable_clock_endpoints if enable_clock_endpoints is not None else False
            )
            self.enable_demo_endpoints = (
                enable_demo_endpoints if enable_demo_endpoints is not None else False
            )
            self.enable_simulator = (
                enable_simulator if enable_simulator is not None else False
            )
            self.allow_query_param_auth = (
                allow_query_param_auth if allow_query_param_auth is not None else False
            )
        else:
            self.enable_clock_endpoints = (
                enable_clock_endpoints if enable_clock_endpoints is not None else True
            )
            self.enable_demo_endpoints = (
                enable_demo_endpoints if enable_demo_endpoints is not None else True
            )
            self.enable_simulator = (
                enable_simulator if enable_simulator is not None else True
            )
            self.allow_query_param_auth = (
                allow_query_param_auth if allow_query_param_auth is not None else True
            )

        self._validate_for_production()

    def is_production(self) -> bool:
        return self.env == "production"

    def is_development(self) -> bool:
        return self.env == "development"

    def is_test(self) -> bool:
        return self.env == "test"

    def _validate_for_production(self) -> None:
        """Enforce strict production hardening invariants."""
        if not self.is_production():
            return

        # 1. Require strong auth token or scoped tokens
        has_token = bool(self.auth_token)
        has_scoped = bool(self.scoped_tokens)
        has_jwt = bool(self.jwt_secret)

        if not (has_token or has_scoped or has_jwt):
            raise SecurityConfigurationError(
                "CARELOOP_ENV=production requires a secure ALEXA_AUTH_TOKEN, "
                "CARELOOP_SCOPED_TOKENS, or CARELOOP_JWT_SECRET. Open access is strictly prohibited."
            )

        if self.auth_token:
            if self.auth_token.lower() in INSECURE_DEFAULT_TOKENS or len(self.auth_token) < 16:
                raise SecurityConfigurationError(
                    f"Insecure or short ALEXA_AUTH_TOKEN ('{self.auth_token[:4]}...') rejected in production. "
                    "Must be at least 16 characters and not a default value."
                )

        # 2. Forbid wildcard CORS with credentials in production
        if "*" in self.allowed_origins:
            raise SecurityConfigurationError(
                "CORS wildcard '*' is prohibited in production. Explicit allowed origins must be configured."
            )

        # 3. Forbid query param auth in production
        if self.allow_query_param_auth:
            raise SecurityConfigurationError(
                "Query parameter authentication (?auth_token=) is prohibited in production. "
                "Tokens must be transmitted via HTTP Authorization headers."
            )

        # 4. Forbid clock manipulation in production
        if self.enable_clock_endpoints:
            raise SecurityConfigurationError(
                "Clock manipulation endpoints (/api/clock/*) must be disabled in production."
            )

        # 5. Forbid demo reset in production
        if self.enable_demo_endpoints:
            raise SecurityConfigurationError(
                "Demo endpoints (/api/demo/*) must be disabled in production."
            )


def load_secrets_from_aws(secret_id: str, region_name: str = "us-east-1") -> Dict[str, str]:
    """
    Fetch secret key-value pairs from AWS Secrets Manager.
    Returns empty dict if boto3 is unavailable or secret cannot be reached.
    """
    try:
        import boto3
        from botocore.exceptions import ClientError
        client = boto3.client("secretsmanager", region_name=region_name)
        response = client.get_secret_value(SecretId=secret_id)
        if "SecretString" in response:
            return json.loads(response["SecretString"])
        return {}
    except Exception as e:
        logger.warning(f"Could not load secrets from AWS Secrets Manager ({secret_id}): {e}")
        return {}


def load_config(env_dict: Optional[Dict[str, str]] = None) -> AppConfig:
    """
    Load configuration from environment variables or AWS Secrets Manager.
    """
    source = os.environ if env_dict is None else env_dict

    env = source.get("CARELOOP_ENV", "development").strip().lower()

    # Attempt to load from AWS Secrets Manager if configured
    aws_secret_id = source.get("AWS_SECRETS_MANAGER_SECRET_ID", "").strip()
    aws_region = source.get("AWS_REGION", "us-east-1").strip()
    secrets: Dict[str, str] = {}
    if aws_secret_id:
        secrets = load_secrets_from_aws(aws_secret_id, aws_region)

    # Resolve auth token
    auth_token = source.get(
        "ALEXA_AUTH_TOKEN", secrets.get("ALEXA_AUTH_TOKEN", "")
    ).strip() or None

    # Resolve scoped tokens
    scoped_tokens_raw = source.get(
        "CARELOOP_SCOPED_TOKENS", secrets.get("CARELOOP_SCOPED_TOKENS", "")
    ).strip()
    scoped_tokens: Dict[str, Dict[str, Any]] = {}
    if scoped_tokens_raw:
        try:
            scoped_tokens = json.loads(scoped_tokens_raw)
        except Exception as e:
            logger.error(f"Failed to parse CARELOOP_SCOPED_TOKENS JSON: {e}")

    # Resolve JWT secret
    jwt_secret = source.get(
        "CARELOOP_JWT_SECRET", secrets.get("CARELOOP_JWT_SECRET", "")
    ).strip() or None

    # Resolve allowed origins
    origins_str = source.get("ALLOWED_ORIGINS", "").strip()
    allowed_origins = [o.strip() for o in origins_str.split(",") if o.strip()]
    if not allowed_origins and env != "production":
        allowed_origins = ["*"]

    # Request body size limit
    max_body_str = source.get("MAX_REQUEST_BODY_SIZE_BYTES", "65536").strip()
    try:
        max_body_size = int(max_body_str)
    except ValueError:
        max_body_size = 65536

    # Rate limits
    rate_rpm_str = source.get("RATE_LIMIT_RPM", "120").strip()
    try:
        rate_limit_rpm = int(rate_rpm_str)
    except ValueError:
        rate_limit_rpm = 120

    notif_rate_str = source.get("NOTIFICATION_RATE_LIMIT_PER_HOUR", "10").strip()
    try:
        notification_rate_limit = int(notif_rate_str)
    except ValueError:
        notification_rate_limit = 10

    # Retention
    event_ret_str = source.get("ROUTINE_EVENT_RETENTION_DAYS", "90").strip()
    try:
        event_retention_days = int(event_ret_str)
    except ValueError:
        event_retention_days = 90

    alert_ret_str = source.get("ALERT_RECORD_RETENTION_DAYS", "180").strip()
    try:
        alert_retention_days = int(alert_ret_str)
    except ValueError:
        alert_retention_days = 180

    # Explicit toggles
    enable_clock = None
    if "ENABLE_CLOCK_ENDPOINTS" in source:
        enable_clock = source["ENABLE_CLOCK_ENDPOINTS"].strip().lower() in ("true", "1", "yes")

    enable_demo = None
    if "ENABLE_DEMO_ENDPOINTS" in source:
        enable_demo = source["ENABLE_DEMO_ENDPOINTS"].strip().lower() in ("true", "1", "yes")

    enable_sim = None
    if "ENABLE_SIMULATOR" in source:
        enable_sim = source["ENABLE_SIMULATOR"].strip().lower() in ("true", "1", "yes")

    allow_query = None
    if "ALLOW_QUERY_PARAM_AUTH" in source:
        allow_query = source["ALLOW_QUERY_PARAM_AUTH"].strip().lower() in ("true", "1", "yes")

    return AppConfig(
        env=env,
        auth_token=auth_token,
        scoped_tokens=scoped_tokens,
        jwt_secret=jwt_secret,
        allowed_origins=allowed_origins,
        max_request_body_size_bytes=max_body_size,
        rate_limit_rpm=rate_limit_rpm,
        notification_rate_limit_per_hour=notification_rate_limit,
        event_retention_days=event_retention_days,
        alert_retention_days=alert_retention_days,
        enable_clock_endpoints=enable_clock,
        enable_demo_endpoints=enable_demo,
        enable_simulator=enable_sim,
        allow_query_param_auth=allow_query,
    )

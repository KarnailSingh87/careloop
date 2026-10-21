"""
Unit and integration tests verifying CareLoop's conformance with official
Amazon Developer Alexa+ Model Context Protocol (MCP) integration requirements.

Covers:
1. MCP Protocol version (2025-11-25) and Streamable HTTP endpoints (/mcp and /v1/mcp).
2. RFC 9728 & RFC 8414 OAuth metadata discovery for Alexa+ Tier 1 and Tier 2 account linking.
3. 401 Challenge with WWW-Authenticate header to trigger Alexa+ app account linking.
4. Tool schema design conventions ("declare only what you honor", valid JSON schemas).
5. Simulator fallback labeling and disclaimer verification.
"""

import pytest
from starlette.testclient import TestClient

from careloop.config import AppConfig
from careloop.server.main import create_app
from careloop.storage.sqlite_store import SQLiteStorage
from careloop.clock import SystemClock


@pytest.fixture
def test_app():
    """Create test application in test mode with SQLite."""
    config = AppConfig(
        env="test",
        auth_token="alexa_test_token_1234567890",
    )
    storage = SQLiteStorage(db_path=":memory:")
    app = create_app(
        storage=storage,
        clock=SystemClock(),
        config=config,
        auth_token="alexa_test_token_1234567890",
    )
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app, raise_server_exceptions=False)


# =============================================================================
# 1. MCP Protocol & Transport Compatibility
# =============================================================================


def test_mcp_routes_exist_for_mcp_and_v1_mcp(test_app):
    """Verify both /mcp and /v1/mcp route aliases are registered for Alexa+ client compatibility."""
    routes = [getattr(r, "path", None) for r in test_app.routes]
    assert "/mcp" in routes
    assert "/v1/mcp" in routes


def test_cors_headers_expose_mcp_session_and_www_authenticate(client):
    """Verify CORS configuration exposes Mcp-Session-Id and WWW-Authenticate headers on actual requests."""
    resp = client.get(
        "/api/mcp/tools",
        headers={
            "Origin": "https://alexa.amazon.com",
            "Authorization": "Bearer alexa_test_token_1234567890",
        },
    )
    assert resp.status_code == 200
    exposed = resp.headers.get("access-control-expose-headers", "")
    assert "Mcp-Session-Id" in exposed
    assert "WWW-Authenticate" in exposed


# =============================================================================
# 2. Metadata Discovery for Alexa+ Account Linking (RFC 9728 & RFC 8414)
# =============================================================================


def test_rfc9728_oauth_protected_resource_metadata(client):
    """Verify /.well-known/oauth-protected-resource returns RFC 9728 compliant discovery document."""
    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    data = resp.json()
    assert "resource" in data
    assert "authorization_servers" in data
    assert isinstance(data["authorization_servers"], list)
    assert "scopes_supported" in data
    assert "bearer_methods_supported" in data
    assert "header" in data["bearer_methods_supported"]


def test_rfc8414_oauth_authorization_server_metadata(client):
    """Verify /.well-known/oauth-authorization-server declares OAuth 2.1 PKCE support for Alexa+."""
    resp = client.get("/.well-known/oauth-authorization-server")
    assert resp.status_code == 200
    data = resp.json()
    assert "issuer" in data
    assert "authorization_endpoint" in data
    assert "token_endpoint" in data
    assert "grant_types_supported" in data
    assert "authorization_code" in data["grant_types_supported"]
    assert "client_credentials" in data["grant_types_supported"]
    assert "code_challenge_methods_supported" in data
    assert "S256" in data["code_challenge_methods_supported"]


# =============================================================================
# 3. Authentication & Account Linking Trigger Pattern
# =============================================================================


def test_unauthenticated_request_triggers_401_with_www_authenticate(client):
    """
    Alexa+ integration requirement: Unauthenticated tool access must respond with
    HTTP 401 and WWW-Authenticate Bearer realm to prompt Alexa app account linking.
    """
    resp = client.post(
        "/api/mcp/call",
        json={"tool": "check_routine_health", "arguments": {"person_id": "dad"}},
    )
    assert resp.status_code == 401
    assert "www-authenticate" in resp.headers
    assert "Bearer" in resp.headers["www-authenticate"]
    assert "CareLoop Alexa+ MCP" in resp.headers["www-authenticate"]


def test_authenticated_request_succeeds(client):
    """Authorized request with valid Bearer token executes successfully."""
    resp = client.post(
        "/api/mcp/call",
        headers={"Authorization": "Bearer alexa_test_token_1234567890"},
        json={"tool": "check_routine_health", "arguments": {"person_id": "dad"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert data["is_error"] is False
    assert data["protocol_version"] == "2025-11-25"


# =============================================================================
# 4. Tool Schema Design Conventions ("Declare Only What You Honor")
# =============================================================================


def test_all_tools_have_valid_schemas_and_descriptions(client):
    """
    Verify all MCP tools follow Alexa+ design guidelines:
    - One tool = one clear intent
    - Non-empty descriptions explaining when to call and what is returned
    - Valid JSON schema with type=object
    """
    resp = client.get(
        "/api/mcp/tools",
        headers={"Authorization": "Bearer alexa_test_token_1234567890"},
    )
    assert resp.status_code == 200
    tools = resp.json()["tools"]
    assert len(tools) >= 8

    tool_names = [t["name"] for t in tools]
    # Verify no duplicate tool names
    assert len(tool_names) == len(set(tool_names))

    for tool in tools:
        assert tool["name"].isidentifier(), f"Tool name {tool['name']} must be a valid identifier"
        assert len(tool["description"].strip()) > 20, f"Tool {tool['name']} must have a meaningful description"
        assert "WHEN TO CALL" in tool["description"], f"Tool {tool['name']} should state when to call"

        schema = tool["inputSchema"]
        assert schema.get("type") == "object", f"Tool {tool['name']} schema must be an object"
        assert "properties" in schema, f"Tool {tool['name']} must declare properties"


def test_tools_return_voice_response_attribute(client):
    """
    Alexa+ multimodal UX requirement: Tool execution results should include
    voice_response or human-friendly natural language for Alexa speech output.
    """
    resp = client.post(
        "/api/mcp/call",
        headers={"Authorization": "Bearer alexa_test_token_1234567890"},
        json={
            "tool": "log_routine_event",
            "arguments": {"person": "dad", "type": "medication"},
        },
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert "voice_response" in result
    assert len(result["voice_response"]) > 0


# =============================================================================
# 5. Simulator Fallback & Simulation Disclaimers
# =============================================================================


def test_simulator_contains_explicit_simulation_labels(client):
    """
    Verify the simulator fallback is explicitly labeled as a simulation harness
    and does not claim to be a live Amazon Alexa+ Echo device.
    """
    resp = client.get("/simulator")
    assert resp.status_code == 200
    html = resp.text
    assert "SIMULATION FALLBACK" in html
    assert "Not an Amazon-certified Alexa+ device" in html
    assert "Local Simulation Fallback" in html

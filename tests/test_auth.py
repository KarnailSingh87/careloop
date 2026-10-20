"""
Unit tests for Alexa+ authentication, CORS, and endpoint format compatibility.
"""

import pytest
from starlette.testclient import TestClient
from careloop.clock import SimulatedClock
from careloop.server.main import create_app
from careloop.storage.sqlite_store import SQLiteStorage


@pytest.fixture
def auth_client(tmp_path):
    db_file = str(tmp_path / "auth_test.db")
    storage = SQLiteStorage(db_path=db_file)
    clock = SimulatedClock()
    token = "test-secret-alexa-token-12345"

    app = create_app(
        storage=storage,
        clock=clock,
        enable_background_loop=False,
        auth_token=token,
    )
    with TestClient(app) as client:
        yield client, token
    storage.close()


def test_public_endpoints_bypass_auth(auth_client):
    client, _ = auth_client

    # /health should be 200 (required for AWS ALB health checks)
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"

    # /simulator should be 200 (interactive developer UI)
    res_sim = client.get("/simulator")
    assert res_sim.status_code == 200

    # / redirects to /simulator
    res_root = client.get("/", follow_redirects=False)
    assert res_root.status_code == 307
    assert res_root.headers["location"] == "/simulator"


def test_protected_endpoints_require_auth(auth_client):
    client, _ = auth_client

    # /mcp returns 401 without auth
    res = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert res.status_code == 401
    assert "Unauthorized" in res.json()["error"]["message"]
    assert "Bearer" in res.headers.get("www-authenticate", "")

    # /v1/mcp alias also requires auth
    res_v1 = client.post("/v1/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert res_v1.status_code == 401

    # /api/state requires auth
    res_state = client.get("/api/state?person=dad")
    assert res_state.status_code == 401

    # /api/mcp/call requires auth
    res_call = client.post("/api/mcp/call", json={"tool": "confirm_ok", "arguments": {"person": "dad"}})
    assert res_call.status_code == 401


def test_auth_via_bearer_header(auth_client):
    client, token = auth_client
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/state?person=dad", headers=headers)
    assert res.status_code == 200
    assert res.json()["person"]["id"] == "dad"


def test_auth_via_alexa_header(auth_client):
    client, token = auth_client
    headers = {"x-alexa-auth-token": token}

    res = client.get("/api/state?person=dad", headers=headers)
    assert res.status_code == 200


def test_auth_via_api_key_header(auth_client):
    client, token = auth_client
    headers = {"x-api-key": token}

    res = client.get("/api/state?person=dad", headers=headers)
    assert res.status_code == 200


def test_auth_via_query_token(auth_client):
    client, token = auth_client

    res = client.get(f"/api/state?person=dad&auth_token={token}")
    assert res.status_code == 200


def test_cors_options_preflight(auth_client):
    client, _ = auth_client

    # Pre-flight OPTIONS request should bypass auth
    res = client.options(
        "/api/mcp/call",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_auth_invalid_tokens_rejected(auth_client):
    client, token = auth_client

    # Partial prefix match must be rejected (avoids timing or prefix vulnerability)
    res_prefix = client.get(
        "/api/state?person=dad",
        headers={"Authorization": f"Bearer {token[:-1]}"},
    )
    assert res_prefix.status_code == 401

    # Empty token rejected
    res_empty = client.get(
        "/api/state?person=dad",
        headers={"Authorization": "Bearer "},
    )
    assert res_empty.status_code == 401

    # Extra character rejected
    res_extra = client.get(
        "/api/state?person=dad",
        headers={"Authorization": f"Bearer {token}x"},
    )
    assert res_extra.status_code == 401

    # Completely wrong token rejected
    res_wrong = client.get(
        "/api/state?person=dad",
        headers={"Authorization": "Bearer completely-wrong-token-abc"},
    )
    assert res_wrong.status_code == 401


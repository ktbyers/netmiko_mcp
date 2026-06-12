"""
Tests for the BearerTokenMiddleware ASGI authentication middleware.

These tests exercise the middleware directly using httpx's ASGI transport, which
constructs real HTTP requests and captures real HTTP responses without starting a
network listener. This validates the full RFC 6750 header parsing and 401 response
formatting without any mocking of the middleware internals.
"""

from typing import Any

import httpx
import pytest

from netmiko_mcp.http_auth import BearerTokenMiddleware

TOKEN = "super-secret-test-token"


async def _ok_app(scope: Any, receive: Any, send: Any) -> None:
    """Minimal ASGI app that always returns HTTP 200 OK."""
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        }
    )
    await send({"type": "http.response.body", "body": b"ok", "more_body": False})


def _make_client(token: str = TOKEN) -> httpx.AsyncClient:
    """Return an httpx AsyncClient backed by the middleware-wrapped ASGI app."""
    app = BearerTokenMiddleware(_ok_app, token)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


@pytest.mark.anyio
async def test_valid_token_passes_through() -> None:
    """A request with the correct bearer token should reach the inner app and return 200."""
    async with _make_client() as client:
        response = await client.get("/mcp", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200


@pytest.mark.anyio
async def test_missing_auth_header_returns_401() -> None:
    """A request without any Authorization header should receive HTTP 401."""
    async with _make_client() as client:
        response = await client.get("/mcp")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_wrong_token_returns_401() -> None:
    """A request with an incorrect bearer token value should receive HTTP 401."""
    async with _make_client() as client:
        response = await client.get("/mcp", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_wrong_scheme_returns_401() -> None:
    """A request using a non-Bearer auth scheme should receive HTTP 401."""
    async with _make_client() as client:
        response = await client.get("/mcp", headers={"Authorization": f"Basic {TOKEN}"})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_empty_bearer_value_returns_401() -> None:
    """A bare 'Bearer ' header with no token value should receive HTTP 401."""
    async with _make_client() as client:
        response = await client.get("/mcp", headers={"Authorization": "Bearer "})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_www_authenticate_header_present_on_401() -> None:
    """HTTP 401 responses must include a WWW-Authenticate: Bearer header per RFC 6750."""
    async with _make_client() as client:
        response = await client.get("/mcp")
    assert response.status_code == 401
    assert "www-authenticate" in response.headers
    assert response.headers["www-authenticate"].startswith("Bearer")


@pytest.mark.anyio
async def test_401_body_is_json() -> None:
    """The 401 response body should be a JSON error object."""
    async with _make_client() as client:
        response = await client.get("/mcp")
    assert response.status_code == 401
    data = response.json()
    assert "error" in data


@pytest.mark.anyio
async def test_bearer_scheme_case_insensitive() -> None:
    """The 'Bearer' scheme prefix check should be case-insensitive per RFC 7235."""
    async with _make_client() as client:
        response = await client.get("/mcp", headers={"Authorization": f"BEARER {TOKEN}"})
    assert response.status_code == 200


@pytest.mark.anyio
async def test_lifespan_scope_passes_through_without_auth() -> None:
    """Non-HTTP ASGI scopes (lifespan) should bypass the auth check entirely."""
    received_lifespan = []

    async def lifespan_app(scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            received_lifespan.append(True)
            event = await receive()
            if event["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})

    middleware = BearerTokenMiddleware(lifespan_app, TOKEN)

    async def fake_receive() -> dict[str, Any]:
        return {"type": "lifespan.startup"}

    sent_messages: list[dict[str, Any]] = []

    async def fake_send(message: Any) -> None:
        sent_messages.append(message)

    await middleware({"type": "lifespan"}, fake_receive, fake_send)

    assert received_lifespan, "Lifespan scope should have reached the inner app"
    assert sent_messages[0]["type"] == "lifespan.startup.complete"

"""
In-process behavioral tests for the Streamable HTTP transport (no device required).

These tests start the real ASGI app returned by ``mcp.streamable_http_app(...)`` on a
loopback uvicorn server in a background thread, then exercise it two ways:

- Raw ``httpx`` requests assert wire-level behavior: whether an ``Mcp-Session-Id`` header
  is issued (the observable effect of the ``http_stateless`` flag for handshake-era
  clients) and whether responses use ``application/json`` (the effect of
  ``http_json_response``).
- The official MCP client drives a full ``initialize`` + tool call to prove tools work
  end-to-end over HTTP, not just stdio.

No network egress and no real devices are involved; only the ``ping`` tool is called.
"""

import contextlib
import socket
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.types import ASGIApp

from netmiko_mcp.server import mcp

# A minimal, protocol-valid JSON-RPC initialize request body. protocolVersion is a
# handshake-era value so that, absent an MCP-Protocol-Version header, the server routes
# by the http_stateless flag rather than the modern (always-stateless) envelope.
_INIT_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "netmiko-mcp-tests", "version": "0.0.0"},
    },
}
_INIT_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def _free_port() -> int:
    """Return an unused TCP port on the loopback interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _build_app(*, stateless: bool, json_response: bool) -> ASGIApp:
    """Build the Streamable HTTP ASGI app with the given transport settings.

    Auth middleware is intentionally omitted: these tests target transport behavior, not
    bearer-token enforcement (which is covered in test_http_auth / test_http_server).
    """
    return mcp.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=json_response,
        stateless_http=stateless,
        host="127.0.0.1",
    )


@contextlib.contextmanager
def _serve(app: ASGIApp) -> Iterator[str]:
    """Run ``app`` on a loopback uvicorn server in a background thread.

    Yields the base URL. uvicorn skips signal-handler installation when not on the main
    thread, so running it in a daemon thread is supported.
    """
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("uvicorn server did not start in time")
            time.sleep(0.02)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_stateless_initialize_issues_no_session_id() -> None:
    """With http_stateless True, an initialize response carries no Mcp-Session-Id header
    and (http_json_response True) uses an application/json content type."""
    app = _build_app(stateless=True, json_response=True)
    with _serve(app) as base_url:
        resp = httpx.post(f"{base_url}/mcp", json=_INIT_BODY, headers=_INIT_HEADERS, timeout=10)

    assert resp.status_code == 200, resp.text
    assert "mcp-session-id" not in {k.lower() for k in resp.headers}
    assert resp.headers["content-type"].lower().startswith("application/json")


def test_stateful_initialize_issues_session_id() -> None:
    """Contrast: with http_stateless False, a handshake-era initialize is assigned an
    Mcp-Session-Id header. This differs from the stateless case only by the flag, proving
    the flag drives the wire behavior rather than the assertion always holding."""
    app = _build_app(stateless=False, json_response=True)
    with _serve(app) as base_url:
        resp = httpx.post(f"{base_url}/mcp", json=_INIT_BODY, headers=_INIT_HEADERS, timeout=10)

    assert resp.status_code == 200, resp.text
    assert "mcp-session-id" in {k.lower() for k in resp.headers}


@pytest.mark.anyio
async def test_stateless_http_client_ping_and_tools() -> None:
    """End-to-end over HTTP with the official MCP client and the default stateless/JSON
    settings: initialize succeeds, ping returns 'pong', and the tool catalog contains the
    netmiko-mcp tools. Proves tools work over HTTP, not just stdio. (Statelessness on the
    wire is asserted separately in test_stateless_initialize_issues_no_session_id.)"""
    app = _build_app(stateless=True, json_response=True)
    with _serve(app) as base_url:
        async with streamable_http_client(f"{base_url}/mcp") as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                ping_result = await session.call_tool("ping", arguments={})
                assert getattr(ping_result.content[0], "text", "") == "pong"

                tools = {t.name for t in (await session.list_tools()).tools}
                assert {"ping", "send_show_command", "list_devices"}.issubset(tools)

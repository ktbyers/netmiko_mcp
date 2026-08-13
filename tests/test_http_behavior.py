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
- A modern ``2026-07-28`` per-request envelope (routing headers + ``params._meta``) drives
  ``tools/list`` and ``tools/call`` to prove the stateless envelope introduced by that
  revision works — a path the handshake-era (``2025-11-25``) tests never trigger.

No network egress and no real devices are involved; only the ``ping`` tool is called.
"""

import contextlib
import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import uvicorn
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.inbound import (
    CLIENT_CAPABILITIES_META_KEY,
    CLIENT_INFO_META_KEY,
    HEADER_MISMATCH,
    INVALID_PARAMS,
    MCP_METHOD_HEADER,
    MCP_NAME_HEADER,
    MCP_PROTOCOL_VERSION_HEADER,
    PROTOCOL_VERSION_META_KEY,
    UNSUPPORTED_PROTOCOL_VERSION,
)
from mcp_types.version import LATEST_MODERN_VERSION
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


def _modern_meta() -> dict[str, Any]:
    """Return the required modern-envelope ``params._meta`` block for the 2026-07-28 revision.

    The modern per-request envelope carries the negotiated protocol version, client
    capabilities, and client info in reserved ``_meta`` keys instead of relying on a prior
    ``initialize`` handshake. These keys are mandatory; the server rejects the request
    without them.
    """
    return {
        PROTOCOL_VERSION_META_KEY: LATEST_MODERN_VERSION,
        CLIENT_CAPABILITIES_META_KEY: {},
        CLIENT_INFO_META_KEY: {"name": "netmiko-mcp-tests", "version": "0.0.0"},
    }


def _modern_headers(method: str, name: str | None = None) -> dict[str, str]:
    """Return headers that route a request to the modern stateless envelope handler.

    An ``mcp-protocol-version`` header outside the handshake set selects
    ``handle_modern_request``; the routable ``mcp-method`` (and ``mcp-name`` for tool
    calls) headers must agree with the JSON-RPC body or the server rejects the request,
    which is what lets gateways route/rate-limit without parsing the body.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        MCP_PROTOCOL_VERSION_HEADER: LATEST_MODERN_VERSION,
        MCP_METHOD_HEADER: method,
    }
    if name is not None:
        headers[MCP_NAME_HEADER] = name
    return headers


def _modern_body(
    request_id: int, method: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build a JSON-RPC request body carrying the modern-envelope ``_meta`` block."""
    body_params: dict[str, Any] = dict(params or {})
    body_params["_meta"] = _modern_meta()
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": body_params}


def test_modern_envelope_tools_work_statelessly() -> None:
    """A modern 2026-07-28 request (routing headers + params._meta envelope, no prior
    initialize handshake) reaches handle_modern_request: tools/list returns the netmiko-mcp
    catalog and tools/call ping returns 'pong', both with no Mcp-Session-Id header and an
    application/json body.

    This exercises the actual stateless envelope introduced by the 2026-07-28 revision,
    which the handshake-era tests (protocolVersion 2025-11-25, no mcp-protocol-version
    header) never trigger — those only exercise the legacy stateless path gated by the
    http_stateless flag. A regression that broke modern-envelope handling, tool
    registration, or the ping tool would fail this test.

    The assertions on the modern result-envelope fields (``resultType`` and the cacheable-
    discovery ``cacheScope`` hint) are what make this test discriminating: the legacy path
    returns a bare ``{"tools": [...]}`` without them, so dropping the modern routing header
    (and falling back to legacy) fails the test rather than silently passing.
    """
    app = _build_app(stateless=True, json_response=True)
    with _serve(app) as base_url:
        list_resp = httpx.post(
            f"{base_url}/mcp",
            json=_modern_body(1, "tools/list"),
            headers=_modern_headers("tools/list"),
            timeout=10,
        )
        ping_resp = httpx.post(
            f"{base_url}/mcp",
            json=_modern_body(2, "tools/call", {"name": "ping", "arguments": {}}),
            headers=_modern_headers("tools/call", "ping"),
            timeout=10,
        )

    assert list_resp.status_code == 200, list_resp.text
    assert "mcp-session-id" not in {k.lower() for k in list_resp.headers}
    assert list_resp.headers["content-type"].lower().startswith("application/json")
    list_result = list_resp.json()["result"]
    # Modern-only result-envelope fields: absent on the legacy path, so their presence
    # proves handle_modern_request served this response rather than the legacy handler.
    assert list_result["resultType"] == "complete"
    assert "cacheScope" in list_result
    tool_names = {t["name"] for t in list_result["tools"]}
    assert {"ping", "send_show_command", "list_devices"}.issubset(tool_names)

    assert ping_resp.status_code == 200, ping_resp.text
    # Each modern request stands on its own: no session id is issued or required.
    assert "mcp-session-id" not in {k.lower() for k in ping_resp.headers}
    ping_result = ping_resp.json()["result"]
    assert ping_result["resultType"] == "complete"
    assert any(part.get("text") == "pong" for part in ping_result["content"])


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        # The modern envelope's params._meta must carry the reserved protocol-version and
        # client-capabilities keys; each of these is a distinct INVALID_PARAMS rejection.
        ("missing_meta", INVALID_PARAMS),
        ("missing_protocol_version_key", INVALID_PARAMS),
        ("missing_client_capabilities_key", INVALID_PARAMS),
        # The routable mcp-method / mcp-name headers must agree with the JSON-RPC body so a
        # gateway can trust them without parsing the body; a disagreement is HEADER_MISMATCH.
        ("method_header_mismatch", HEADER_MISMATCH),
        ("name_header_mismatch", HEADER_MISMATCH),
        # A protocol version the server does not implement is a structured rejection, not a
        # silent downgrade.
        ("unsupported_protocol_version", UNSUPPORTED_PROTOCOL_VERSION),
    ],
)
def test_modern_envelope_rejects_malformed_requests(case: str, expected_code: int) -> None:
    """Each malformed modern request is rejected with HTTP 400 and the documented JSON-RPC
    error code, and no session id is issued.

    Every case starts from an otherwise-valid modern request and perturbs exactly one thing
    (a missing envelope key, a routing header that disagrees with the body, or an
    unsupported protocol version) so the observed error code is attributable to that single
    defect. Asserting on the specific SDK error-code constants (rather than merely 'some
    error') means a validator that silently accepted a malformed envelope — or returned the
    wrong code — would fail this test.
    """
    body: dict[str, Any]
    headers: dict[str, str]
    if case == "missing_meta":
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        headers = _modern_headers("tools/list")
    elif case == "missing_protocol_version_key":
        meta = {k: v for k, v in _modern_meta().items() if k != PROTOCOL_VERSION_META_KEY}
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": meta}}
        headers = _modern_headers("tools/list")
    elif case == "missing_client_capabilities_key":
        meta = {k: v for k, v in _modern_meta().items() if k != CLIENT_CAPABILITIES_META_KEY}
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": meta}}
        headers = _modern_headers("tools/list")
    elif case == "method_header_mismatch":
        # Body says tools/list but the routing header claims tools/call.
        body = _modern_body(1, "tools/list")
        headers = _modern_headers("tools/call")
    elif case == "name_header_mismatch":
        # Body calls ping but the routing header names a different tool.
        body = _modern_body(1, "tools/call", {"name": "ping", "arguments": {}})
        headers = _modern_headers("tools/call", "not_ping")
    elif case == "unsupported_protocol_version":
        meta = {**_modern_meta(), PROTOCOL_VERSION_META_KEY: "2099-01-01"}
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": meta}}
        headers = {**_modern_headers("tools/list"), MCP_PROTOCOL_VERSION_HEADER: "2099-01-01"}
    else:  # pragma: no cover - guards against an unhandled parametrize id
        raise AssertionError(f"unhandled case {case}")

    app = _build_app(stateless=True, json_response=True)
    with _serve(app) as base_url:
        resp = httpx.post(f"{base_url}/mcp", json=body, headers=headers, timeout=10)

    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == expected_code
    # A rejected modern request must not issue a session id.
    assert "mcp-session-id" not in {k.lower() for k in resp.headers}


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

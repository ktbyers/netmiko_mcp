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
import json
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
    INVALID_REQUEST,
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


def _build_app(*, stateless: bool, json_response: bool, host: str = "127.0.0.1") -> ASGIApp:
    """Build the Streamable HTTP ASGI app with the given transport settings.

    ``host`` is the value server.py passes to streamable_http_app(); it selects the SDK's
    transport-security posture (a loopback value auto-enables DNS-rebinding Host/Origin
    checks) and is independent of the address uvicorn actually binds to in _serve().

    Auth middleware is intentionally omitted: these tests target transport behavior, not
    bearer-token enforcement (which is covered in test_http_auth / test_http_server).
    """
    return mcp.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=json_response,
        stateless_http=stateless,
        host=host,
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


def test_legacy_sse_response_when_json_response_disabled() -> None:
    """With http_json_response False, a handshake-era request is answered as a
    text/event-stream and the JSON-RPC result is delivered inside an SSE data frame.

    This is the behavioral counterpart to test_stateless_initialize_issues_no_session_id
    (which uses json_response True and asserts application/json). Together they form a
    contrasting pair: the same initialize request under the two flag values yields two
    different content types, so the result is only explainable by the flag actually driving
    the response encoding rather than a constant. Previously only the wiring (that the flag
    reaches streamable_http_app) was tested via mocks; nothing confirmed the SSE body on
    the wire.
    """
    app = _build_app(stateless=True, json_response=False)
    with _serve(app) as base_url:
        resp = httpx.post(f"{base_url}/mcp", json=_INIT_BODY, headers=_INIT_HEADERS, timeout=10)

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].lower().startswith("text/event-stream")
    # The JSON-RPC result must round-trip through the SSE data frame(s), proving the stream
    # carries a usable response and not merely a different content-type header.
    data_lines = [
        line[len("data:") :].strip() for line in resp.text.splitlines() if line.startswith("data:")
    ]
    assert data_lines, f"no SSE data frame in response: {resp.text!r}"
    payload = json.loads("".join(data_lines))
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == _INIT_BODY["id"]
    assert "result" in payload


def test_modern_envelope_stays_json_when_json_response_disabled() -> None:
    """The http_json_response flag governs only the legacy handshake path. A modern
    2026-07-28 request is a single request/response envelope and is answered as
    application/json even when json_response is False.

    Contrast with test_legacy_sse_response_when_json_response_disabled, which sends the
    same-configured server an initialize handshake and gets text/event-stream: the differing
    content types for the two request styles against one json_response=False app prove the
    flag's effect is scoped to legacy clients, matching the documented behavior that modern
    clients are always stateless single-response.
    """
    app = _build_app(stateless=True, json_response=False)
    with _serve(app) as base_url:
        resp = httpx.post(
            f"{base_url}/mcp",
            json=_modern_body(1, "tools/list"),
            headers=_modern_headers("tools/list"),
            timeout=10,
        )

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].lower().startswith("application/json")
    assert resp.json()["result"]["resultType"] == "complete"


def test_stateless_serves_independent_requests_without_session() -> None:
    """The stateless transport answers each request on its own — no prior initialize
    handshake, no shared session — even across separate client connections.

    Two standalone tools/call requests are sent from two independent httpx clients, each
    with its own connection pool, so there is no connection or session affinity carried
    between them. Both succeed and neither is issued a session id. This is the property a
    round-robin load balancer or a serverless deployment relies on: request N+1 must not
    depend on state established by request N. The paired
    test_stateful_rejects_standalone_request_without_session shows the same standalone
    request is refused when statelessness is off, so this test fails if that property
    silently regresses to stateful.
    """
    app = _build_app(stateless=True, json_response=True)
    responses: list[httpx.Response] = []
    with _serve(app) as base_url:
        for request_id in (1, 2):
            body = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": "ping", "arguments": {}},
            }
            # A fresh client per request => a distinct connection, so a success cannot rely
            # on session/connection affinity established by the other request.
            with httpx.Client() as client:
                responses.append(
                    client.post(f"{base_url}/mcp", json=body, headers=_INIT_HEADERS, timeout=10)
                )

    for resp in responses:
        assert resp.status_code == 200, resp.text
        assert "mcp-session-id" not in {k.lower() for k in resp.headers}
        content = resp.json()["result"]["content"]
        assert any(part.get("text") == "pong" for part in content)


def test_stateful_rejects_standalone_request_without_session() -> None:
    """Contrast for test_stateless_serves_independent_requests_without_session: with
    statelessness off, a standalone tools/call that carries no session id (and performed no
    initialize handshake) is refused with a 'Missing session ID' error.

    This is what makes the stateless test meaningful — the success there is attributable to
    statelessness removing the per-session requirement, not to the server never needing a
    session. The two tests send an identical request and differ only in the http_stateless
    flag, so the opposite outcomes are only explainable by that flag.
    """
    app = _build_app(stateless=False, json_response=True)
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "ping", "arguments": {}},
    }
    with _serve(app) as base_url, httpx.Client() as client:
        resp = client.post(f"{base_url}/mcp", json=body, headers=_INIT_HEADERS, timeout=10)

    assert resp.status_code == 400, resp.text
    error = resp.json()["error"]
    assert error["code"] == INVALID_REQUEST
    assert "session" in error["message"].lower()


def test_localhost_bind_rejects_foreign_host_and_origin() -> None:
    """On a loopback bind the SDK auto-enables DNS-rebinding protection: a request whose
    Host or Origin is not localhost is refused (421 / 403), while a legitimate localhost
    Host is served (200).

    Passing host=127.0.0.1 to streamable_http_app() is what activates this in server.py.
    The positive control (default Host -> 200) makes the rejections meaningful rather than a
    blanket refusal, and the paired non-localhost test shows the behavior is driven by the
    host bind. This is a browser-only attack surface (Host/Origin are forbidden headers a
    page cannot forge), so it is defense-in-depth behind the bearer token rather than a
    control a headless server-to-server deployment relies on.
    """
    app = _build_app(stateless=True, json_response=True, host="127.0.0.1")
    with _serve(app) as base_url:
        # httpx derives Host from base_url (127.0.0.1:<port>), an allowed value.
        allowed = httpx.post(f"{base_url}/mcp", json=_INIT_BODY, headers=_INIT_HEADERS, timeout=10)
        foreign_host = httpx.post(
            f"{base_url}/mcp",
            json=_INIT_BODY,
            headers={**_INIT_HEADERS, "Host": "evil.example.com"},
            timeout=10,
        )
        foreign_origin = httpx.post(
            f"{base_url}/mcp",
            json=_INIT_BODY,
            headers={**_INIT_HEADERS, "Origin": "http://evil.example.com"},
            timeout=10,
        )

    assert allowed.status_code == 200, allowed.text
    assert foreign_host.status_code == 421
    assert foreign_origin.status_code == 403


def test_non_localhost_bind_does_not_auto_enable_rebinding_protection() -> None:
    """The auto-protection is keyed on a loopback bind. With host=0.0.0.0 the SDK does not
    enable it, so a foreign Host is accepted (200).

    This documents the operational reality that an operator binding a routable interface (or
    fronting the server with a reverse proxy that forwards a non-localhost Host) is relying
    on the bearer token / TLS rather than Host validation. It is also the contrast that
    proves the localhost test's 421/403 rejections come from the host bind: a failure here
    would mean the SDK tightened its defaults, which is worth re-evaluating deliberately.
    """
    app = _build_app(stateless=True, json_response=True, host="0.0.0.0")
    with _serve(app) as base_url:
        resp = httpx.post(
            f"{base_url}/mcp",
            json=_INIT_BODY,
            headers={**_INIT_HEADERS, "Host": "evil.example.com"},
            timeout=10,
        )

    assert resp.status_code == 200, resp.text


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

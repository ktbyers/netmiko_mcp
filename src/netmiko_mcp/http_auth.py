"""
RFC 6750 bearer token authentication middleware for the Netmiko MCP HTTP transport.

Every incoming HTTP request must carry an Authorization header of the form:

    Authorization: Bearer <token>

Requests that are missing the header, use the wrong scheme, or carry an incorrect
token receive an HTTP 401 response with a WWW-Authenticate: Bearer header, also per
RFC 6750.

The token comparison uses hmac.compare_digest to avoid timing side-channel attacks.
Non-HTTP ASGI scopes (lifespan, etc.) pass through without any authentication check.
"""

import hmac

from starlette.types import ASGIApp, Receive, Scope, Send


class BearerTokenMiddleware:
    """Pure ASGI middleware that enforces RFC 6750 bearer token authentication.

    Wrap any ASGI application with this middleware to require callers to present a
    valid bearer token on every HTTP request. The token is supplied at construction
    time and should be read from the NETMIKO_MCP_HTTP_BEARER_TOKEN environment
    variable by the caller — never from a config file.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._token_bytes = token.encode("utf-8")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            if not self._is_authorized(scope):
                await self._send_401(send)
                return
        await self._app(scope, receive, send)

    def _is_authorized(self, scope: Scope) -> bool:
        """Return True if the request carries a valid bearer token.

        Iterates the raw ASGI headers list looking for an Authorization header.
        The scheme check is case-insensitive (RFC 7235 §2.1). Token comparison
        uses hmac.compare_digest to prevent timing attacks.
        """
        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        for name, value in headers:
            if name.lower() == b"authorization":
                auth = value.decode("latin-1")
                if auth[:7].lower() == "bearer ":
                    candidate = auth[7:].encode("utf-8")
                    return hmac.compare_digest(candidate, self._token_bytes)
                return False
        return False

    async def _send_401(self, send: Send) -> None:
        """Emit an HTTP 401 Unauthorized response per RFC 6750 §3."""
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b'Bearer realm="netmiko-mcp"'),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"error": "Unauthorized"}',
                "more_body": False,
            }
        )

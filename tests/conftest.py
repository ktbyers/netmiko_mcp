import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Iterator

import httpx
import pytest
import yaml
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# Absolute path to the tests directory, derived from this file's location so
# that all fixture paths are CWD-independent and work correctly in CI.
_TESTS_DIR = Path(__file__).parent.resolve()
_ETC_DIR = _TESTS_DIR / "etc"
_INVENTORY_FILE = _ETC_DIR / ".netmiko.yml"
_RESPONSES_FILE = _ETC_DIR / "responses.yml"


@pytest.fixture(scope="session")
def test_config() -> dict[str, Any]:
    """Load expected test values from tests/etc/responses.yml.

    Session-scoped so the file is read once per pytest run and the resulting
    dict is shared across all tests.
    """
    with _RESPONSES_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)  # type: ignore[no-any-return]


@pytest.fixture
def anyio_backend() -> str:
    """Specify the backend for pytest-anyio."""
    return "asyncio"


def _make_mcp_client(
    extra_env: dict[str, str] | None = None,
) -> AsyncGenerator[ClientSession, None]:
    """Factory for MCP client fixtures with optional extra environment variables."""

    async def _client() -> AsyncGenerator[ClientSession, None]:
        test_env = {**os.environ}
        test_env["NETMIKO_MCP_CONFIG"] = str(_ETC_DIR / "netmiko-mcp.yml")
        # Override inventory_file and command_file with absolute paths so the
        # server subprocess resolves them correctly regardless of its CWD.
        test_env["NETMIKO_MCP_INVENTORY_FILE"] = str(_ETC_DIR / ".netmiko.yml")
        test_env["NETMIKO_MCP_COMMAND_FILE"] = str(_ETC_DIR / "commands.yml")
        if extra_env:
            test_env.update(extra_env)

        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-c", "from netmiko_mcp.server import main; main()"],
            env=test_env,
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    return _client()


def _require_inventory() -> None:
    """Skip the calling test if the live test inventory file is absent.

    Prevents the server subprocess from starting and falling back to
    ~/.netmiko.yml when tests/etc/.netmiko.yml does not exist.
    """
    if not _INVENTORY_FILE.is_file():
        pytest.skip(
            "tests/etc/.netmiko.yml not found — create this file with device "
            "credentials before running live tests"
        )


@pytest.fixture
async def mcp_client() -> AsyncGenerator[ClientSession, None]:
    """MCP client using default settings (max_workers=10)."""
    _require_inventory()
    async for client in _make_mcp_client():
        yield client


@pytest.fixture
async def mcp_client_sequential() -> AsyncGenerator[ClientSession, None]:
    """MCP client with max_workers=1 for sequential execution — used to verify threading."""
    _require_inventory()
    async for client in _make_mcp_client({"NETMIKO_MCP_MAX_WORKERS": "1"}):
        yield client


@pytest.fixture
async def mcp_client_low_threshold() -> AsyncGenerator[ClientSession, None]:
    """MCP client with save_threshold=5 so any real show command triggers auto-save."""
    _require_inventory()
    async for client in _make_mcp_client({"NETMIKO_MCP_SAVE_THRESHOLD": "5"}):
        yield client


def _free_port() -> int:
    """Return an unused TCP port on the loopback interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def mcp_http_server() -> Iterator[tuple[str, str]]:
    """Start the server as a subprocess on the streamable-http transport and yield
    ``(base_url, bearer_token)``.

    A random bearer token is generated per run and passed only via the subprocess
    environment (never logged). The same test config/inventory/command wiring as the
    stdio fixtures is reused. The fixture waits until the HTTP stack answers before
    yielding, and terminates the subprocess on teardown.
    """
    _require_inventory()
    token = secrets.token_hex(32)
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    test_env = {**os.environ}
    test_env["NETMIKO_MCP_CONFIG"] = str(_ETC_DIR / "netmiko-mcp.yml")
    test_env["NETMIKO_MCP_INVENTORY_FILE"] = str(_ETC_DIR / ".netmiko.yml")
    test_env["NETMIKO_MCP_COMMAND_FILE"] = str(_ETC_DIR / "commands.yml")
    test_env["NETMIKO_MCP_TRANSPORT"] = "streamable-http"
    test_env["NETMIKO_MCP_HTTP_HOST"] = "127.0.0.1"
    test_env["NETMIKO_MCP_HTTP_PORT"] = str(port)
    test_env["NETMIKO_MCP_HTTP_PATH"] = "/mcp"
    test_env["NETMIKO_MCP_HTTP_BEARER_TOKEN"] = token

    proc = subprocess.Popen(
        [sys.executable, "-c", "from netmiko_mcp.server import main; main()"],
        env=test_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 20
        while True:
            if proc.poll() is not None:
                out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
                raise RuntimeError(f"HTTP server subprocess exited early:\n{out}")
            try:
                # Any HTTP response (e.g. 401 from the auth middleware) means the ASGI
                # stack is serving and ready to accept MCP requests.
                httpx.get(f"{base_url}/mcp", timeout=0.5)
                break
            except httpx.HTTPError:
                if time.monotonic() > deadline:
                    raise RuntimeError("HTTP server did not become ready in time")
                time.sleep(0.1)
        yield base_url, token
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()

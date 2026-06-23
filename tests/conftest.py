import os
import sys
from pathlib import Path
from typing import Any, AsyncGenerator

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
            f"{_INVENTORY_FILE} not found — create this file with device "
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

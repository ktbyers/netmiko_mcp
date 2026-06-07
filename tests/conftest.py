import os
import sys
from typing import AsyncGenerator

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


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
        test_env["NETMIKO_MCP_CONFIG"] = os.path.abspath("tests/etc/netmiko-mcp.yml")
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


@pytest.fixture
async def mcp_client() -> AsyncGenerator[ClientSession, None]:
    """MCP client using default settings (max_workers=10)."""
    async for client in _make_mcp_client():
        yield client


@pytest.fixture
async def mcp_client_sequential() -> AsyncGenerator[ClientSession, None]:
    """MCP client with max_workers=1 for sequential execution — used to verify threading."""
    async for client in _make_mcp_client({"NETMIKO_MCP_MAX_WORKERS": "1"}):
        yield client

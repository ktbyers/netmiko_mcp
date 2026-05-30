import sys
from typing import AsyncGenerator

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.fixture
def anyio_backend() -> str:
    """Specify the backend for pytest-anyio."""
    return "asyncio"


@pytest.fixture
async def mcp_client() -> AsyncGenerator[ClientSession, None]:
    """Provide a fully initialized MCP ClientSession connected to the local server."""
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from netmiko_mcp.server import main; main()"],
        env={**os.environ}
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session

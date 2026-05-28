import sys
import pytest
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_ping_integration() -> None:
    """Integration test using the official MCP client over stdio pipes."""
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from netmiko_mcp.server import main; main()"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool("ping", arguments={})

            assert len(result.content) == 1
            assert result.content[0].type == "text"
            assert result.content[0].text == "pong"

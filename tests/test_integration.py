import pytest
from mcp.client.session import ClientSession


@pytest.mark.anyio
async def test_ping_integration(mcp_client: ClientSession) -> None:
    """Integration test using the official MCP client over stdio pipes."""
    result = await mcp_client.call_tool("ping", arguments={})

    assert len(result.content) == 1
    assert result.content[0].type == "text"
    assert result.content[0].text == "pong"

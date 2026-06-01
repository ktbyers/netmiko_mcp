import json
import os

import pytest
from mcp.client.session import ClientSession


@pytest.mark.anyio
async def test_ping_integration(mcp_client: ClientSession) -> None:
    """Integration test using the official MCP client over stdio pipes."""
    result = await mcp_client.call_tool("ping", arguments={})

    assert len(result.content) == 1
    assert result.content[0].type == "text"
    assert getattr(result.content[0], "text", "") == "pong"


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_live_device_connection(mcp_client: ClientSession) -> None:
    """
    End-to-end integration test against a real network device.
    This simulates an MCP client asking for the inventory, and then executing a command.
    """
    # Test the inventory list
    inv_result = await mcp_client.call_tool("list_devices", arguments={"device_or_group": "cisco1"})

    assert len(inv_result.content) == 1
    assert inv_result.content[0].type == "text"
    inventory = json.loads(getattr(inv_result.content[0], "text", ""))

    # Assert cisco1 was found and credentials were sanitized
    assert "cisco1" in inventory
    assert inventory["cisco1"]["device_type"] == "cisco_ios"
    assert "password" not in inventory["cisco1"]

    # Test actual execution via the MCP tool
    cmd_result = await mcp_client.call_tool(
        "send_show_command",
        arguments={"device_name": "cisco1", "command": "show version", "use_textfsm": False},
    )

    assert len(cmd_result.content) == 1
    assert cmd_result.content[0].type == "text"
    output = getattr(cmd_result.content[0], "text", "")

    # Assert the router actually responded with standard IOS output
    assert (
        "Cisco IOS Software" in output or "Cisco Internetwork Operating System Software" in output
    )

    # Test piped execution via the MCP tool
    piped_result = await mcp_client.call_tool(
        "send_show_command",
        arguments={
            "device_name": "cisco1",
            "command": "show version | include Version",
            "use_textfsm": False,
        },
    )

    assert len(piped_result.content) == 1
    assert piped_result.content[0].type == "text"
    piped_output = getattr(piped_result.content[0], "text", "")

    # Assert the output was correctly filtered by the router
    assert "Version 15.5(3)M8" in piped_output
    assert "uptime is" not in piped_output  # Proves the output was filtered

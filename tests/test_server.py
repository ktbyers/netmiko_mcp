from typing import Any
from unittest.mock import patch

from netmiko_mcp.server import list_devices, mcp, ping, send_show_command


def test_ping_tool() -> None:
    """Test that the ping tool returns the expected response."""
    assert ping() == "pong"


def test_mcp_initialization() -> None:
    """Test that the FastMCP server is initialized with the correct name."""
    assert mcp.name == "netmiko-mcp"


@patch("netmiko_mcp.server.get_sanitized_inventory")
def test_list_devices_tool(mock_get_sanitized: Any) -> None:
    """Test that the list_devices tool delegates to the inventory module."""
    mock_get_sanitized.return_value = '{"rtr1": {"host": "1.1.1.1"}}'
    assert list_devices("rtr1") == '{"rtr1": {"host": "1.1.1.1"}}'
    mock_get_sanitized.assert_called_once_with("rtr1")


@patch("netmiko_mcp.server.run_show_command")
def test_send_show_command_tool(mock_run_show: Any) -> None:
    """Test that the send_show_command tool delegates to the connection module."""
    mock_run_show.return_value = "Router Uptime 5 days"
    assert send_show_command("rtr1", "show version") == "Router Uptime 5 days"
    mock_run_show.assert_called_once_with("rtr1", "show version")

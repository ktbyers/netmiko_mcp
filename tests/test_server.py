from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from netmiko_mcp.server import (
    _validate_startup,
    list_device_outputs,
    list_devices,
    list_groups,
    mcp,
    ping,
    read_device_output,
    send_show_command,
    send_show_command_to_group,
)


# ---------------------------------------------------------------------------
# _validate_startup
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.server.settings")
def test_validate_startup_missing_command_file(mock_settings: Any, tmp_path: Path) -> None:
    """Server should refuse to start if command_file does not exist."""
    mock_settings.command_file = str(tmp_path / "nonexistent.yml")
    with pytest.raises(SystemExit, match="Startup Error"):
        _validate_startup()


@patch("netmiko_mcp.server.settings")
def test_validate_startup_valid_command_file(mock_settings: Any, tmp_path: Path) -> None:
    """Server should start successfully when command_file exists."""
    cmd_file = tmp_path / "commands.yml"
    cmd_file.write_text("allowed_commands: []\n", encoding="utf-8")
    mock_settings.command_file = str(cmd_file)
    _validate_startup()  # should not raise


@patch("netmiko_mcp.server.settings")
def test_validate_startup_error_message_contains_path(mock_settings: Any, tmp_path: Path) -> None:
    """The startup error message should include the configured path."""
    bad_path = str(tmp_path / "missing.yml")
    mock_settings.command_file = bad_path
    with pytest.raises(SystemExit, match=bad_path):
        _validate_startup()


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.server.get_group_names")
def test_list_groups_tool(mock_get_groups: Any) -> None:
    """list_groups should return a JSON-encoded list of group name strings."""
    import json

    mock_get_groups.return_value = ["cisco", "arista"]
    result = list_groups()
    assert json.loads(result) == ["cisco", "arista"]
    mock_get_groups.assert_called_once_with()


@patch("netmiko_mcp.server.log_tool_invocation")
@patch("netmiko_mcp.server.get_group_names")
def test_list_groups_tool_logs_invocation(mock_get_groups: Any, mock_log: Any) -> None:
    """list_groups should emit an audit record with no arguments."""
    mock_get_groups.return_value = []
    list_groups()
    mock_log.assert_called_once_with(tool="list_groups", arguments={})


@patch("netmiko_mcp.server.get_group_names")
def test_list_groups_tool_handles_error(mock_get_groups: Any) -> None:
    """list_groups should return a JSON-encoded error when get_group_names raises ValueError."""
    import json

    mock_get_groups.side_effect = ValueError("Inventory file not found: No file")
    result = list_groups()
    parsed = json.loads(result)
    assert "error" in parsed
    assert "Inventory file not found" in parsed["error"]


def test_ping_tool() -> None:
    """Test that the ping tool returns the expected response."""
    assert ping() == "pong"


@patch("netmiko_mcp.server.log_tool_invocation")
def test_ping_tool_logs_invocation(mock_log: Any) -> None:
    """ping should emit an audit record for the tool invocation."""
    ping()
    mock_log.assert_called_once_with(tool="ping", arguments={})


def test_mcp_initialization() -> None:
    """Test that the FastMCP server is initialized with the correct name."""
    assert mcp.name == "netmiko-mcp"


@patch("netmiko_mcp.server.get_sanitized_inventory")
def test_list_devices_tool(mock_get_sanitized: Any) -> None:
    """Test that the list_devices tool delegates to the inventory module."""
    mock_get_sanitized.return_value = '{"rtr1": {"host": "1.1.1.1"}}'
    assert list_devices("rtr1") == '{"rtr1": {"host": "1.1.1.1"}}'
    mock_get_sanitized.assert_called_once_with("rtr1")


@patch("netmiko_mcp.server.log_tool_invocation")
@patch("netmiko_mcp.server.get_sanitized_inventory")
def test_list_devices_tool_logs_invocation(mock_inv: Any, mock_log: Any) -> None:
    """list_devices should emit an audit record including the device_or_group argument."""
    mock_inv.return_value = "{}"
    list_devices("all")
    mock_log.assert_called_once_with(tool="list_devices", arguments={"device_or_group": "all"})


@patch("netmiko_mcp.server.run_show_command")
def test_send_show_command_tool(mock_run_show: Any) -> None:
    """Test that the send_show_command tool delegates to the connection module."""
    # Mock returning structured data
    mock_run_show.return_value = [{"intf": "Gi0/0", "status": "up"}]
    assert send_show_command("rtr1", "show ip int brief", True) == [
        {"intf": "Gi0/0", "status": "up"}
    ]
    mock_run_show.assert_called_once_with("rtr1", "show ip int brief", True)


@patch("netmiko_mcp.server.run_show_command_on_group")
def test_send_show_command_to_group_tool(mock_run_group: Any) -> None:
    """Test that send_show_command_to_group delegates to the connection module."""
    mock_run_group.return_value = {"rtr1": "IOS output", "rtr2": "IOS output"}
    result = send_show_command_to_group("core", "show version")
    assert result == {"rtr1": "IOS output", "rtr2": "IOS output"}
    mock_run_group.assert_called_once_with("core", "show version", False, False)


@patch("netmiko_mcp.server._list_device_outputs")
def test_list_device_outputs_tool(mock_list: Any) -> None:
    """Test that list_device_outputs delegates to the connection module."""
    mock_list.return_value = {"cisco1": ["show_version_20260607.txt"]}
    result = list_device_outputs("cisco")
    assert result == {"cisco1": ["show_version_20260607.txt"]}
    mock_list.assert_called_once_with("cisco")


@patch("netmiko_mcp.server.log_tool_invocation")
@patch("netmiko_mcp.server._list_device_outputs")
def test_list_device_outputs_tool_logs_invocation(mock_list: Any, mock_log: Any) -> None:
    """list_device_outputs should emit an audit record including device_or_group."""
    mock_list.return_value = {}
    list_device_outputs("cisco")
    mock_log.assert_called_once_with(
        tool="list_device_outputs", arguments={"device_or_group": "cisco"}
    )


@patch("netmiko_mcp.server._read_device_output")
def test_read_device_output_tool(mock_read: Any) -> None:
    """Test that read_device_output delegates to the connection module with offset and limit."""
    mock_read.return_value = "Lines 1-3 of 3.\nIOS output content"
    result = read_device_output("cisco1", "show_version_20260607.txt", offset=0, limit=500)
    assert result == "Lines 1-3 of 3.\nIOS output content"
    mock_read.assert_called_once_with("cisco1", "show_version_20260607.txt", 0, 500)


@patch("netmiko_mcp.server._read_device_output")
def test_read_device_output_tool_default_pagination(mock_read: Any) -> None:
    """read_device_output uses offset=0, limit=500 when called with no pagination args."""
    mock_read.return_value = "Lines 1-3 of 3.\ncontent"
    read_device_output("cisco1", "show_version_20260607.txt")
    mock_read.assert_called_once_with("cisco1", "show_version_20260607.txt", 0, 500)


@patch("netmiko_mcp.server.log_tool_invocation")
@patch("netmiko_mcp.server._read_device_output")
def test_read_device_output_tool_logs_invocation(mock_read: Any, mock_log: Any) -> None:
    """read_device_output should emit an audit record including offset and limit."""
    mock_read.return_value = "content"
    read_device_output("cisco1", "show_version_20260607.txt", offset=100, limit=200)
    mock_log.assert_called_once_with(
        tool="read_device_output",
        arguments={
            "device_name": "cisco1",
            "filename": "show_version_20260607.txt",
            "offset": 100,
            "limit": 200,
        },
    )


@patch("netmiko_mcp.server.configure_audit_logger")
@patch("netmiko_mcp.server.settings")
def test_main_calls_configure_audit_logger(mock_settings: Any, mock_configure: Any) -> None:
    """main() should call configure_audit_logger before starting the server."""
    from netmiko_mcp.server import main
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix=".yml", delete=False) as f:
        f.write(b"allowed_commands: []\n")
        tmp = f.name
    try:
        mock_settings.command_file = tmp
        with patch("netmiko_mcp.server.mcp"):
            main()
        mock_configure.assert_called_once()
    finally:
        os.unlink(tmp)

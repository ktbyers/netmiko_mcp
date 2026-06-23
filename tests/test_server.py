from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import netmiko_mcp.server as server_module
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
def test_validate_startup_missing_command_file_http_raises(
    mock_settings: Any, tmp_path: Path
) -> None:
    """In HTTP mode, _validate_startup should raise SystemExit if command_file does not exist."""
    mock_settings.command_file = str(tmp_path / "nonexistent.yml")
    mock_settings.transport = "streamable-http"
    mock_settings.http_auth_enabled = False
    with pytest.raises(SystemExit, match="Startup Error"):
        _validate_startup()


@patch("netmiko_mcp.server.settings")
def test_validate_startup_missing_command_file_stdio_does_not_raise(
    mock_settings: Any, tmp_path: Path
) -> None:
    """In stdio mode, _validate_startup should not raise for a missing command_file.
    The error is stored in _startup_error so the MCP handshake can complete.
    """
    original = server_module._startup_error
    try:
        mock_settings.command_file = str(tmp_path / "nonexistent.yml")
        mock_settings.transport = "stdio"
        mock_settings.http_auth_enabled = False
        _validate_startup()  # should not raise
    finally:
        server_module._startup_error = original


@patch("netmiko_mcp.server.settings")
def test_validate_startup_valid_command_file(mock_settings: Any, tmp_path: Path) -> None:
    """Server should start successfully when command_file exists."""
    cmd_file = tmp_path / "commands.yml"
    cmd_file.write_text("allowed_commands: []\n", encoding="utf-8")
    mock_settings.command_file = str(cmd_file)
    mock_settings.transport = "stdio"
    mock_settings.http_auth_enabled = False
    _validate_startup()  # should not raise


@patch("netmiko_mcp.server.settings")
def test_validate_startup_error_message_contains_path(mock_settings: Any, tmp_path: Path) -> None:
    """In HTTP mode, the startup error message should include the configured path."""
    bad_path = str(tmp_path / "missing.yml")
    mock_settings.command_file = bad_path
    mock_settings.transport = "streamable-http"
    mock_settings.http_auth_enabled = False
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
    mock_run_show.return_value = [{"intf": "Gi0/0", "status": "up"}]
    assert send_show_command("rtr1", "show ip int brief", True) == [
        {"intf": "Gi0/0", "status": "up"}
    ]
    mock_run_show.assert_called_once_with("rtr1", "show ip int brief", True, False)


@patch("netmiko_mcp.server.run_show_command")
def test_send_show_command_tool_explicit_save(mock_run_show: Any) -> None:
    """save_output=True is passed through to run_show_command."""
    mock_run_show.return_value = "Output saved as 'show_version_20260622_120000.txt'."
    result = send_show_command("rtr1", "show version", save_output=True)
    assert result == "Output saved as 'show_version_20260622_120000.txt'."
    mock_run_show.assert_called_once_with("rtr1", "show version", False, True)


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
        mock_settings.transport = "stdio"
        mock_settings.http_auth_enabled = False
        with patch("netmiko_mcp.server.mcp"):
            main()
        mock_configure.assert_called_once()
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------------------
# _startup_error — stdio degraded mode
# ---------------------------------------------------------------------------


def test_ping_returns_startup_error_when_set() -> None:
    """ping should return the startup error string instead of 'pong' when set."""
    original = server_module._startup_error
    try:
        server_module._startup_error = (
            "Startup Error: command_file '~/commands.yml' does not exist."
        )
        result = ping()
        assert result == server_module._startup_error
    finally:
        server_module._startup_error = original


def test_ping_returns_pong_when_no_startup_error() -> None:
    """ping should return 'pong' when _startup_error is None."""
    original = server_module._startup_error
    try:
        server_module._startup_error = None
        assert ping() == "pong"
    finally:
        server_module._startup_error = original


def test_list_groups_returns_startup_error_when_set() -> None:
    """list_groups should return the startup error string when _startup_error is set."""
    original = server_module._startup_error
    try:
        server_module._startup_error = "Startup Error: command_file missing."
        assert list_groups() == server_module._startup_error
    finally:
        server_module._startup_error = original


def test_list_devices_returns_startup_error_when_set() -> None:
    """list_devices should return the startup error string when _startup_error is set."""
    original = server_module._startup_error
    try:
        server_module._startup_error = "Startup Error: command_file missing."
        assert list_devices() == server_module._startup_error
    finally:
        server_module._startup_error = original


def test_send_show_command_returns_startup_error_when_set() -> None:
    """send_show_command should return the startup error string when _startup_error is set."""
    original = server_module._startup_error
    try:
        server_module._startup_error = "Startup Error: command_file missing."
        result = send_show_command("rtr1", "show version")
        assert result == server_module._startup_error
    finally:
        server_module._startup_error = original


def test_send_show_command_to_group_returns_startup_error_when_set() -> None:
    """send_show_command_to_group should return the startup error string when _startup_error is set."""
    original = server_module._startup_error
    try:
        server_module._startup_error = "Startup Error: command_file missing."
        assert send_show_command_to_group("core", "show version") == server_module._startup_error
    finally:
        server_module._startup_error = original


def test_list_device_outputs_returns_startup_error_when_set() -> None:
    """list_device_outputs should return the startup error string when _startup_error is set."""
    original = server_module._startup_error
    try:
        server_module._startup_error = "Startup Error: command_file missing."
        assert list_device_outputs("cisco") == server_module._startup_error
    finally:
        server_module._startup_error = original


def test_read_device_output_returns_startup_error_when_set() -> None:
    """read_device_output should return the startup error string when _startup_error is set."""
    original = server_module._startup_error
    try:
        server_module._startup_error = "Startup Error: command_file missing."
        result = read_device_output("cisco1", "show_version.txt")
        assert result == server_module._startup_error
    finally:
        server_module._startup_error = original


@patch("netmiko_mcp.server.settings")
def test_validate_startup_sets_startup_error_on_missing_command_file_stdio(
    mock_settings: Any,
) -> None:
    """_validate_startup() should set _startup_error and not raise when command_file
    is missing in stdio mode."""
    original = server_module._startup_error
    try:
        mock_settings.command_file = "/nonexistent/commands.yml"
        mock_settings.transport = "stdio"
        mock_settings.http_auth_enabled = False
        _validate_startup()
        assert server_module._startup_error is not None
        assert "command_file" in server_module._startup_error
    finally:
        server_module._startup_error = original


@patch("netmiko_mcp.server.configure_audit_logger")
@patch("netmiko_mcp.server.settings")
def test_main_sets_startup_error_on_missing_command_file_stdio(
    mock_settings: Any, mock_configure: Any
) -> None:
    """main() should still start the MCP server when command_file is missing in stdio mode."""
    original = server_module._startup_error
    try:
        mock_settings.command_file = "/nonexistent/commands.yml"
        mock_settings.transport = "stdio"
        mock_settings.http_auth_enabled = False
        with patch("netmiko_mcp.server.mcp") as mock_mcp:
            from netmiko_mcp.server import main

            main()
            mock_mcp.run.assert_called_once_with(transport="stdio")
    finally:
        server_module._startup_error = original


@patch("netmiko_mcp.server.settings")
def test_validate_startup_raises_on_missing_command_file_http(
    mock_settings: Any, tmp_path: Any
) -> None:
    """_validate_startup() should raise SystemExit for missing command_file in HTTP mode."""
    mock_settings.transport = "streamable-http"
    mock_settings.command_file = str(tmp_path / "nonexistent.yml")
    mock_settings.http_auth_enabled = False
    with pytest.raises(SystemExit, match="command_file"):
        _validate_startup()

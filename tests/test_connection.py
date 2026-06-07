from pathlib import Path
from unittest.mock import MagicMock, patch

from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

from netmiko_mcp.connection import (
    _sanitize_command_for_filename,
    _save_device_output,
    run_show_command,
    run_show_command_on_group,
)


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
def test_run_show_command_success(
    mock_get_params: MagicMock, mock_connect: MagicMock, mock_validate: MagicMock
) -> None:
    """Test that a command is executed successfully and returns output."""
    mock_validate.return_value = True
    mock_get_params.return_value = {"host": "1.1.1.1", "device_type": "cisco_ios"}

    # Mock the context manager behavior of ConnectHandler
    mock_net_connect = MagicMock()
    mock_net_connect.send_command.return_value = "GigabitEthernet0/0 up up"
    mock_connect.return_value.__enter__.return_value = mock_net_connect

    result = run_show_command("rtr1", "show ip int brief")

    assert result == "GigabitEthernet0/0 up up"
    mock_connect.assert_called_once_with(host="1.1.1.1", device_type="cisco_ios")
    mock_net_connect.send_command.assert_called_once_with("show ip int brief", use_textfsm=False)


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
def test_run_show_command_textfsm(
    mock_get_params: MagicMock, mock_connect: MagicMock, mock_validate: MagicMock
) -> None:
    """Test that textfsm parsed data is correctly serialized to JSON."""
    mock_validate.return_value = True
    mock_get_params.return_value = {"host": "1.1.1.1"}

    mock_net_connect = MagicMock()
    # Simulate textfsm returning a list of dicts
    mock_net_connect.send_command.return_value = [{"intf": "Gi0/0", "status": "up"}]
    mock_connect.return_value.__enter__.return_value = mock_net_connect

    result = run_show_command("rtr1", "show ip int brief", use_textfsm=True)

    # It should return the list of dicts directly, not a JSON string
    assert isinstance(result, list)
    assert result[0]["intf"] == "Gi0/0"
    mock_net_connect.send_command.assert_called_once_with("show ip int brief", use_textfsm=True)


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.get_device_params")
def test_run_show_command_inventory_error(
    mock_get_params: MagicMock, mock_validate: MagicMock
) -> None:
    """Test that an inventory failure is caught and returned as a string."""
    mock_validate.return_value = True
    mock_get_params.side_effect = ValueError("Device not found")

    result = run_show_command("bad_router", "show version")
    assert result == "Inventory Error: Device not found"


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
def test_run_show_command_auth_error(
    mock_get_params: MagicMock, mock_connect: MagicMock, mock_validate: MagicMock
) -> None:
    """Test that an authentication failure is caught and returned as a string."""
    mock_validate.return_value = True
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.side_effect = NetmikoAuthenticationException("Auth failed")

    result = run_show_command("rtr1", "show version")
    assert result == "Connection Error: Authentication failed for device 'rtr1'."


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
def test_run_show_command_timeout_error(
    mock_get_params: MagicMock, mock_connect: MagicMock, mock_validate: MagicMock
) -> None:
    """Test that a timeout failure is caught and returned as a string."""
    mock_validate.return_value = True
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.side_effect = NetmikoTimeoutException("Timeout")

    result = run_show_command("rtr1", "show version")
    assert result == "Connection Error: Connection to device 'rtr1' timed out."


@patch("netmiko_mcp.connection.validate_command")
def test_run_show_command_security_block(mock_validate: MagicMock) -> None:
    """Test that a blocked command returns a Security Error string."""
    mock_validate.return_value = False

    result = run_show_command("rtr1", "reload")
    assert result == "Security Error: Command 'reload' is not permitted."


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
def test_run_show_command_unexpected_exception(
    mock_get_params: MagicMock, mock_connect: MagicMock, mock_validate: MagicMock
) -> None:
    """Test that an unexpected exception is caught and returned as an Execution Error string."""
    mock_validate.return_value = True
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.side_effect = RuntimeError("unexpected SSH negotiation failure")

    result = run_show_command("rtr1", "show version")
    assert isinstance(result, str)
    assert result.startswith("Execution Error:")
    assert "unexpected SSH negotiation failure" in result


# ---------------------------------------------------------------------------
# _sanitize_command_for_filename
# ---------------------------------------------------------------------------


def test_sanitize_command_spaces_become_underscores() -> None:
    assert _sanitize_command_for_filename("show version") == "show_version"


def test_sanitize_command_multi_word() -> None:
    assert _sanitize_command_for_filename("show ip interface brief") == "show_ip_interface_brief"


def test_sanitize_command_special_chars_replaced() -> None:
    result = _sanitize_command_for_filename("show ip route 10.0.0.0")
    assert result == "show_ip_route_10_0_0_0"


def test_sanitize_command_truncated_to_50() -> None:
    long_cmd = "show " + "a" * 60
    result = _sanitize_command_for_filename(long_cmd)
    assert len(result) == 50


# ---------------------------------------------------------------------------
# _save_device_output
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.connection.settings")
def test_save_device_output_creates_file(mock_settings: MagicMock, tmp_path: Path) -> None:
    """Test that _save_device_output writes output to the correct path."""
    mock_settings.save_output_dir = str(tmp_path)
    file_path = _save_device_output("cisco1", "show version", "IOS output here")
    saved = Path(file_path)
    assert saved.exists()
    assert saved.parent.name == "cisco1"
    assert saved.read_text(encoding="utf-8") == "IOS output here"


@patch("netmiko_mcp.connection.settings")
def test_save_device_output_permissions(mock_settings: MagicMock, tmp_path: Path) -> None:
    """Test that directories and files are created with restrictive permissions."""
    mock_settings.save_output_dir = str(tmp_path / "output")
    file_path = _save_device_output("cisco1", "show version", "IOS output")
    saved = Path(file_path)
    # File: owner read/write only (0o600)
    assert oct(saved.stat().st_mode & 0o777) == oct(0o600)
    # Device subdirectory: owner only (0o700)
    assert oct(saved.parent.stat().st_mode & 0o777) == oct(0o700)
    # Base output directory: owner only (0o700)
    assert oct(saved.parent.parent.stat().st_mode & 0o777) == oct(0o700)


@patch("netmiko_mcp.connection.settings")
def test_save_device_output_json_for_structured(mock_settings: MagicMock, tmp_path: Path) -> None:
    """Test that list/dict output is serialized to JSON in the saved file."""
    mock_settings.save_output_dir = str(tmp_path)
    output = [{"intf": "Gi0/0", "status": "up"}]
    file_path = _save_device_output("cisco1", "show ip int brief", output)
    import json

    content = json.loads(Path(file_path).read_text(encoding="utf-8"))
    assert content == output


# ---------------------------------------------------------------------------
# run_show_command_on_group
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.connection.validate_command")
def test_run_show_command_on_group_security_block(mock_validate: MagicMock) -> None:
    """Test that a blocked command returns a security error without connecting."""
    mock_validate.return_value = False
    result = run_show_command_on_group("core", "reload")
    assert "error" in result
    assert "Security Error" in result["error"]


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.get_device_names")
def test_run_show_command_on_group_inventory_error(
    mock_names: MagicMock, mock_validate: MagicMock
) -> None:
    """Test that an inventory error is returned cleanly."""
    mock_validate.return_value = True
    mock_names.side_effect = ValueError("Group 'bad' not found")
    result = run_show_command_on_group("bad", "show version")
    assert "error" in result
    assert "Inventory Error" in result["error"]


@patch("netmiko_mcp.connection.settings")
@patch("netmiko_mcp.connection.run_show_command")
@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.get_device_names")
def test_run_show_command_on_group_success(
    mock_names: MagicMock,
    mock_validate: MagicMock,
    mock_run: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """Test successful concurrent execution across multiple devices."""
    mock_validate.return_value = True
    mock_names.return_value = ["rtr1", "rtr2"]
    mock_settings.max_workers = 10
    mock_run.side_effect = lambda name, cmd, tf: f"output from {name}"
    result = run_show_command_on_group("core", "show version")
    assert result["rtr1"] == "output from rtr1"
    assert result["rtr2"] == "output from rtr2"


@patch("netmiko_mcp.connection.settings")
@patch("netmiko_mcp.connection.run_show_command")
@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.get_device_names")
def test_run_show_command_on_group_partial_failure(
    mock_names: MagicMock,
    mock_validate: MagicMock,
    mock_run: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """Test that one device failing does not prevent results from other devices."""
    mock_validate.return_value = True
    mock_names.return_value = ["rtr1", "rtr2"]
    mock_settings.max_workers = 10

    def side_effect(name: str, cmd: str, tf: bool) -> str:
        if name == "rtr2":
            raise RuntimeError("connection dropped")
        return "output from rtr1"

    mock_run.side_effect = side_effect
    result = run_show_command_on_group("core", "show version")
    assert result["rtr1"] == "output from rtr1"
    assert "Execution Error" in result["rtr2"]


@patch("netmiko_mcp.connection.settings")
@patch("netmiko_mcp.connection.run_show_command")
@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.get_device_names")
def test_run_show_command_on_group_save_output(
    mock_names: MagicMock,
    mock_validate: MagicMock,
    mock_run: MagicMock,
    mock_settings: MagicMock,
    tmp_path: Path,
) -> None:
    """Test that save_output=True writes files and returns file paths."""
    mock_validate.return_value = True
    mock_names.return_value = ["rtr1"]
    mock_settings.max_workers = 10
    mock_settings.save_output_dir = str(tmp_path)
    mock_run.return_value = "IOS output"

    result = run_show_command_on_group("core", "show version", save_output=True)
    assert "rtr1" in result
    assert result["rtr1"].startswith("Saved to:")
    saved_path = Path(result["rtr1"].replace("Saved to: ", ""))
    assert saved_path.exists()
    assert saved_path.read_text(encoding="utf-8") == "IOS output"

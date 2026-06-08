import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

from netmiko_mcp.audit import (
    REASON_ALLOWED,
    REASON_DENY_MATCH,
)
from netmiko_mcp.security import ValidationResult
from netmiko_mcp.connection import (
    _sanitize_command_for_filename,
    _save_device_output,
    list_device_outputs,
    read_device_output,
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
    mock_validate.return_value = ValidationResult(allowed=True, reason=REASON_ALLOWED)
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
    mock_validate.return_value = ValidationResult(allowed=True, reason=REASON_ALLOWED)
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
    mock_validate.return_value = ValidationResult(allowed=True, reason=REASON_ALLOWED)
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
    mock_validate.return_value = ValidationResult(allowed=True, reason=REASON_ALLOWED)
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
    mock_validate.return_value = ValidationResult(allowed=True, reason=REASON_ALLOWED)
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.side_effect = NetmikoTimeoutException("Timeout")

    result = run_show_command("rtr1", "show version")
    assert result == "Connection Error: Connection to device 'rtr1' timed out."


@patch("netmiko_mcp.connection.validate_command")
def test_run_show_command_security_block(mock_validate: MagicMock) -> None:
    """Test that a blocked command returns a Security Error string."""
    mock_validate.return_value = ValidationResult(allowed=False, reason=REASON_DENY_MATCH)

    result = run_show_command("rtr1", "reload")
    assert result == "Security Error: Command 'reload' is not permitted."


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
def test_run_show_command_unexpected_exception(
    mock_get_params: MagicMock, mock_connect: MagicMock, mock_validate: MagicMock
) -> None:
    """Test that an unexpected exception is caught and returned as an Execution Error string."""
    mock_validate.return_value = ValidationResult(allowed=True, reason=REASON_ALLOWED)
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
    mock_validate.return_value = ValidationResult(allowed=False, reason=REASON_DENY_MATCH)
    result = run_show_command_on_group("core", "reload")
    assert "error" in result
    assert "Security Error" in result["error"]


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.get_device_names")
def test_run_show_command_on_group_empty_device_list(
    mock_names: MagicMock, mock_validate: MagicMock
) -> None:
    """An empty device list returns an empty dict without attempting any connections."""
    mock_validate.return_value = ValidationResult(allowed=True, reason=REASON_ALLOWED)
    mock_names.return_value = []
    result = run_show_command_on_group("empty_group", "show version")
    assert result == {}


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.get_device_names")
def test_run_show_command_on_group_inventory_error(
    mock_names: MagicMock, mock_validate: MagicMock
) -> None:
    """Test that an inventory error is returned cleanly."""
    mock_validate.return_value = ValidationResult(allowed=True, reason=REASON_ALLOWED)
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
    mock_validate.return_value = ValidationResult(allowed=True, reason=REASON_ALLOWED)
    mock_names.return_value = ["rtr1", "rtr2"]
    mock_settings.max_workers = 10
    mock_run.side_effect = lambda name, cmd, tf, **kw: f"output from {name}"
    result = run_show_command_on_group("core", "show version")
    assert result["rtr1"] == "output from rtr1"
    assert result["rtr2"] == "output from rtr2"


@patch("netmiko_mcp.connection.settings")
@patch("netmiko_mcp.connection.run_show_command")
@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.get_device_names")
def test_run_show_command_on_group_all_devices_fail(
    mock_names: MagicMock,
    mock_validate: MagicMock,
    mock_run: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """When every device raises an exception every result is an Execution Error string."""
    mock_validate.return_value = ValidationResult(allowed=True, reason=REASON_ALLOWED)
    mock_names.return_value = ["rtr1", "rtr2", "rtr3"]
    mock_settings.max_workers = 10
    mock_run.side_effect = RuntimeError("connection refused")

    result = run_show_command_on_group("cisco", "show version")

    assert len(result) == 3
    for device in ["rtr1", "rtr2", "rtr3"]:
        assert device in result
        assert "Execution Error" in result[device]


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
    mock_validate.return_value = ValidationResult(allowed=True, reason=REASON_ALLOWED)
    mock_names.return_value = ["rtr1", "rtr2"]
    mock_settings.max_workers = 10

    def side_effect(name: str, cmd: str, tf: bool, **kw: Any) -> str:
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
    mock_validate.return_value = ValidationResult(allowed=True, reason=REASON_ALLOWED)
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


@patch("netmiko_mcp.connection.settings")
@patch("netmiko_mcp.connection.run_show_command")
@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.get_device_names")
def test_run_show_command_on_group_textfsm_propagated(
    mock_names: MagicMock,
    mock_validate: MagicMock,
    mock_run: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """use_textfsm=True must be passed through to every run_show_command call."""
    mock_validate.return_value = ValidationResult(allowed=True, reason=REASON_ALLOWED)
    mock_names.return_value = ["rtr1", "rtr2", "rtr3"]
    mock_settings.max_workers = 10
    mock_run.return_value = [{"intf": "Gi0/0", "status": "up"}]

    run_show_command_on_group("cisco", "show ip int brief", use_textfsm=True)

    assert mock_run.call_count == 3
    for call in mock_run.call_args_list:
        _name, _cmd, tf = call.args
        assert tf is True, f"Expected use_textfsm=True but got {tf}"


def test_run_show_command_on_group_max_workers_enforced() -> None:
    """max_workers=1 forces sequential execution, measurably slower than max_workers=4."""
    delay = 0.2
    devices = ["rtr1", "rtr2", "rtr3", "rtr4"]

    def slow_run(name: str, cmd: str, tf: bool, **kw: Any) -> str:
        time.sleep(delay)
        return f"output from {name}"

    timings: dict[int, float] = {}

    for workers in [1, 4]:
        with (
            patch("netmiko_mcp.connection.settings") as ms,
            patch(
                "netmiko_mcp.connection.validate_command",
                return_value=ValidationResult(allowed=True, reason=REASON_ALLOWED),
            ),
            patch("netmiko_mcp.connection.get_device_names", return_value=devices),
            patch("netmiko_mcp.connection.run_show_command", side_effect=slow_run),
        ):
            ms.max_workers = workers
            start = time.monotonic()
            run_show_command_on_group("cisco", "show version")
            timings[workers] = time.monotonic() - start

    # max_workers=1: sequential, ~4 * delay = ~0.8s
    # max_workers=4: parallel,  ~1 * delay = ~0.2s
    # Assert parallel is at least 2x faster as a conservative threshold.
    assert timings[4] < timings[1] / 2, (
        f"max_workers=4 ({timings[4]:.2f}s) not 2x faster than max_workers=1 ({timings[1]:.2f}s)"
    )


# ---------------------------------------------------------------------------
# list_device_outputs
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.connection.settings")
@patch("netmiko_mcp.connection.get_device_names")
def test_list_device_outputs_single_device(
    mock_names: MagicMock, mock_settings: MagicMock, tmp_path: Path
) -> None:
    """Single device with saved files returns them sorted newest-first."""
    mock_names.return_value = ["cisco1"]
    mock_settings.save_output_dir = str(tmp_path)
    device_dir = tmp_path / "cisco1"
    device_dir.mkdir()
    (device_dir / "show_version_20260607_120000.txt").write_text("old")
    (device_dir / "show_version_20260607_130000.txt").write_text("new")

    result = list_device_outputs("cisco1")
    assert result == {
        "cisco1": [
            "show_version_20260607_130000.txt",
            "show_version_20260607_120000.txt",
        ]
    }


@patch("netmiko_mcp.connection.settings")
@patch("netmiko_mcp.connection.get_device_names")
def test_list_device_outputs_no_saved_dir(
    mock_names: MagicMock, mock_settings: MagicMock, tmp_path: Path
) -> None:
    """Device with no saved directory returns empty list."""
    mock_names.return_value = ["cisco1"]
    mock_settings.save_output_dir = str(tmp_path)
    result = list_device_outputs("cisco1")
    assert result == {"cisco1": []}


@patch("netmiko_mcp.connection.settings")
@patch("netmiko_mcp.connection.get_device_names")
def test_list_device_outputs_empty_dir(
    mock_names: MagicMock, mock_settings: MagicMock, tmp_path: Path
) -> None:
    """Device directory exists but is empty returns empty list."""
    mock_names.return_value = ["cisco1"]
    mock_settings.save_output_dir = str(tmp_path)
    (tmp_path / "cisco1").mkdir()
    result = list_device_outputs("cisco1")
    assert result == {"cisco1": []}


@patch("netmiko_mcp.connection.settings")
@patch("netmiko_mcp.connection.get_device_names")
def test_list_device_outputs_group(
    mock_names: MagicMock, mock_settings: MagicMock, tmp_path: Path
) -> None:
    """Group resolves to multiple devices, each listed independently."""
    mock_names.return_value = ["cisco1", "cisco2", "cisco3"]
    mock_settings.save_output_dir = str(tmp_path)
    for device in ["cisco1", "cisco2"]:
        d = tmp_path / device
        d.mkdir()
        (d / "show_version_20260607_120000.txt").write_text("output")

    result = list_device_outputs("cisco")
    assert result["cisco1"] == ["show_version_20260607_120000.txt"]
    assert result["cisco2"] == ["show_version_20260607_120000.txt"]
    assert result["cisco3"] == []


@patch("netmiko_mcp.connection.get_device_names")
def test_list_device_outputs_inventory_error(mock_names: MagicMock) -> None:
    """Invalid group name returns an error dict."""
    mock_names.side_effect = ValueError("Group 'bad' not found")
    result = list_device_outputs("bad")
    assert "error" in result
    assert "Inventory Error" in result["error"]


# ---------------------------------------------------------------------------
# read_device_output
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.connection.settings")
def test_read_device_output_success(mock_settings: MagicMock, tmp_path: Path) -> None:
    """Valid filename returns the file content."""
    mock_settings.save_output_dir = str(tmp_path)
    device_dir = tmp_path / "cisco1"
    device_dir.mkdir()
    (device_dir / "show_version_20260607_120000.txt").write_text(
        "IOS output here", encoding="utf-8"
    )

    result = read_device_output("cisco1", "show_version_20260607_120000.txt")
    assert result == "IOS output here"


@patch("netmiko_mcp.connection.settings")
def test_read_device_output_path_traversal_slash(mock_settings: MagicMock, tmp_path: Path) -> None:
    """Filename containing a slash is blocked."""
    mock_settings.save_output_dir = str(tmp_path)
    result = read_device_output("cisco1", "../../../etc/passwd")
    assert result.startswith("Security Error")


@patch("netmiko_mcp.connection.settings")
def test_read_device_output_path_traversal_dotdot(mock_settings: MagicMock, tmp_path: Path) -> None:
    """Filename containing '..' is blocked."""
    mock_settings.save_output_dir = str(tmp_path)
    result = read_device_output("cisco1", "..")
    assert result.startswith("Security Error")


@patch("netmiko_mcp.connection.settings")
def test_read_device_output_file_not_found(mock_settings: MagicMock, tmp_path: Path) -> None:
    """Non-existent file returns a clear error message."""
    mock_settings.save_output_dir = str(tmp_path)
    (tmp_path / "cisco1").mkdir()
    result = read_device_output("cisco1", "nonexistent.txt")
    assert "not found" in result
    assert "cisco1" in result


@patch("netmiko_mcp.connection.settings")
def test_read_device_output_device_not_found(mock_settings: MagicMock, tmp_path: Path) -> None:
    """Non-existent device directory returns a clear error message."""
    mock_settings.save_output_dir = str(tmp_path)
    result = read_device_output("nonexistent_device", "show_version.txt")
    assert "No saved output found" in result
    assert "nonexistent_device" in result


@patch("netmiko_mcp.connection.save_channel_transcript")
@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
@patch("netmiko_mcp.connection.settings")
def test_run_show_command_transcript_captured(
    mock_settings: MagicMock,
    mock_get_params: MagicMock,
    mock_connect: MagicMock,
    mock_validate: MagicMock,
    mock_transcript: MagicMock,
) -> None:
    """When audit_log_read_transcript is True, save_channel_transcript should be called."""
    mock_settings.audit_log_read_transcript = True
    mock_validate.return_value = ValidationResult(allowed=True, reason=REASON_ALLOWED)
    mock_get_params.return_value = {"host": "1.1.1.1", "device_type": "cisco_ios"}

    mock_net_connect = MagicMock()
    mock_net_connect.send_command.return_value = "IOS output"
    mock_connect.return_value.__enter__.return_value = mock_net_connect

    result = run_show_command("rtr1", "show version")

    assert result == "IOS output"
    mock_transcript.assert_called_once()
    call_args = mock_transcript.call_args
    assert call_args.args[1] == "rtr1"  # device_name


@patch("netmiko_mcp.connection.save_channel_transcript")
@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
@patch("netmiko_mcp.connection.settings")
def test_run_show_command_no_transcript_when_disabled(
    mock_settings: MagicMock,
    mock_get_params: MagicMock,
    mock_connect: MagicMock,
    mock_validate: MagicMock,
    mock_transcript: MagicMock,
) -> None:
    """When audit_log_read_transcript is False, save_channel_transcript should not be called."""
    mock_settings.audit_log_read_transcript = False
    mock_validate.return_value = ValidationResult(allowed=True, reason=REASON_ALLOWED)
    mock_get_params.return_value = {"host": "1.1.1.1", "device_type": "cisco_ios"}

    mock_net_connect = MagicMock()
    mock_net_connect.send_command.return_value = "IOS output"
    mock_connect.return_value.__enter__.return_value = mock_net_connect

    run_show_command("rtr1", "show version")
    mock_transcript.assert_not_called()

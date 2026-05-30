from typing import Any
from unittest.mock import patch

from netmiko_mcp.security import validate_command


def test_validate_command_default_allowed() -> None:
    """Test that default canonical commands are allowed."""
    assert validate_command("show ip interface brief") is True
    assert validate_command("ping 8.8.8.8") is True


def test_validate_command_abbreviations_denied() -> None:
    """Test that abbreviated commands are denied."""
    assert validate_command("sh ip int br") is False
    assert validate_command("p 8.8.8.8") is False


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
        "allowed_commands": ["display "],  # Huawei/Comware syntax
        "denied_commands": ["reboot"],
    }

    # Defaults should now fail
    assert validate_command("show ip int brief") is False

    # Custom allowed should pass
    assert validate_command("display interface brief") is True

    # Custom denied should fail
    assert validate_command("display interface brief reboot") is False

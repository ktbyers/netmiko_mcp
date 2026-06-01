import os
from typing import Any
from unittest.mock import patch
import pytest
from pydantic_core import ValidationError

from netmiko_mcp.config import McpConfig, load_config


def test_mcp_config_defaults() -> None:
    """Test that McpConfig loads with the correct default values."""
    config = McpConfig()
    assert config.inventory_type == "netmiko_tools"
    assert config.inventory_file is None
    assert config.command_file == "~/commands.yml"


def test_mcp_config_validation() -> None:
    """Test that McpConfig strictly validates inventory_type."""
    with pytest.raises(ValidationError):
        # Should fail because only 'netmiko_tools' is permitted by the Literal
        McpConfig(inventory_type="invalid_type")  # type: ignore


@patch("netmiko_mcp.config.load_yaml_file")
@patch("os.path.isfile")
def test_load_config_from_yaml(mock_isfile: Any, mock_load_yaml: Any) -> None:
    """Test that load_config correctly parses an explicitly discovered YAML file."""
    mock_isfile.return_value = True
    # Simulate the YAML file returning these exact keys
    mock_load_yaml.return_value = {
        "NETMIKO_MCP_INVENTORY_TYPE": "netmiko_tools",
        "NETMIKO_MCP_INVENTORY_FILE": "/custom/path.yml",
        "NETMIKO_MCP_COMMAND_FILE": "/custom/commands.yml",
    }

    config = load_config()
    assert config.inventory_file == "/custom/path.yml"
    assert config.command_file == "/custom/commands.yml"


@patch.dict(
    os.environ,
    {
        "NETMIKO_MCP_INVENTORY_FILE": "/env/path.yml",
        "NETMIKO_MCP_COMMAND_FILE": "/env/commands.yml",
    },
)
def test_mcp_config_env_vars() -> None:
    """Test that McpConfig natively reads from NETMIKO_MCP_ environment variables."""
    # We instantiate directly to test pydantic-settings native env reading
    config = McpConfig()
    assert config.inventory_file == "/env/path.yml"
    assert config.command_file == "/env/commands.yml"

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from netmiko.utilities import load_yaml_file


class McpConfig(BaseModel):
    """
    Global configuration for the Netmiko MCP server.
    """

    inventory_type: str = Field(default="netmiko_yaml")
    inventory_file: str = Field(default="~/.netmiko.yml")
    command_file: str = Field(default="~/commands.yml")
    encryption_key_env_var: str = Field(default="NETMIKO_TOOLS_KEY")
    allow_config_changes: bool = Field(default=False)
    allow_pipe: bool = Field(default=False)
    allow_regex: bool = Field(default=False)


def load_config() -> McpConfig:
    """
    Load the global MCP configuration.

    Order of precedence:
    1. NETMIKO_MCP_CONFIG environment variable (if set)
    2. ~/.netmiko-mcp.yml
    3. Default values
    """
    config_path = os.environ.get("NETMIKO_MCP_CONFIG")

    if not config_path:
        default_path = Path.home() / ".netmiko-mcp.yml"
        if default_path.is_file():
            config_path = str(default_path)

    if config_path and os.path.isfile(config_path):
        yaml_data: dict[str, Any] = load_yaml_file(config_path)  # type: ignore
        return McpConfig(**yaml_data)

    # Return defaults if no file is found
    return McpConfig()


# Global singleton configuration object loaded at startup
settings = load_config()

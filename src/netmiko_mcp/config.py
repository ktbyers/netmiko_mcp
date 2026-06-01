import os
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from netmiko.utilities import load_yaml_file


class McpConfig(BaseSettings):
    """
    Global configuration for the Netmiko MCP server.
    """

    model_config = SettingsConfigDict(
        env_prefix="NETMIKO_MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    inventory_type: Literal["netmiko_yaml"] = Field(
        default="netmiko_yaml",
        validation_alias="NETMIKO_MCP_INVENTORY_TYPE",
    )
    inventory_file: str = Field(
        default="~/.netmiko.yml",
        validation_alias="NETMIKO_MCP_INVENTORY_FILE",
    )
    command_file: str = Field(
        default="~/commands.yml",
        validation_alias="NETMIKO_MCP_COMMAND_FILE",
    )
    encryption_key_env_var: str = Field(
        default="NETMIKO_TOOLS_KEY",
        validation_alias="NETMIKO_MCP_ENCRYPTION_KEY_ENV_VAR",
    )
    allow_config_changes: bool = Field(
        default=False,
        validation_alias="NETMIKO_MCP_ALLOW_CONFIG_CHANGES",
    )
    allow_pipe: bool = Field(
        default=False,
        validation_alias="NETMIKO_MCP_ALLOW_PIPE",
    )
    allow_regex: bool = Field(
        default=False,
        validation_alias="NETMIKO_MCP_ALLOW_REGEX",
    )


def load_config() -> McpConfig:
    """
    Load the global MCP configuration.

    Order of precedence:
    1. NETMIKO_MCP_CONFIG environment variable (if set)
    2. ~/.netmiko-mcp.yml
    3. Default values
    """
    config_path_str = os.environ.get("NETMIKO_MCP_CONFIG")

    if config_path_str:
        config_path = Path(config_path_str).expanduser()
    else:
        config_path = Path.home() / ".netmiko-mcp.yml"

    if config_path.is_file():
        yaml_data: dict[str, Any] = load_yaml_file(str(config_path))  # type: ignore
        return McpConfig(**yaml_data)

    # Return defaults if no file is found
    return McpConfig()


# Global singleton configuration object loaded at startup
settings = load_config()

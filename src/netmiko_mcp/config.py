import os
from pathlib import Path
from typing import Literal, Tuple, Type

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class McpConfig(BaseSettings):
    """
    Global configuration for the Netmiko MCP server.
    """

    model_config = SettingsConfigDict(
        env_prefix="NETMIKO_MCP_",
        extra="ignore",
    )

    inventory_type: Literal["netmiko_tools"] = Field(default="netmiko_tools")
    inventory_file: str | None = Field(default=None)
    command_file: str = Field(default="~/commands.yml")
    allow_pipe: bool = Field(default=False)
    unsafe_chars: list[str] = Field(default=[";", "\n", "\r", "&"])
    pipe_modifiers: list[str] = Field(default=["include", "exclude", "section", "begin", "count"])

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """
        Define the exact priority order for settings sources.
        Environment variables (NETMIKO_MCP_*) always take precedence over the YAML
        config file. Use environment variables or your MCP client's env injection.
        A .env file is not supported.
        """
        config_path_str = os.environ.get("NETMIKO_MCP_CONFIG")
        if config_path_str:
            config_path = Path(config_path_str).expanduser()
        else:
            config_path = Path.home() / ".netmiko-mcp.yml"

        yaml_source = None
        if config_path.is_file():
            yaml_source = YamlConfigSettingsSource(settings_cls, yaml_file=config_path)

        sources = [init_settings, env_settings]
        if yaml_source:
            sources.append(yaml_source)

        return tuple(sources)


# The global singleton configuration object loaded at startup
settings = McpConfig()

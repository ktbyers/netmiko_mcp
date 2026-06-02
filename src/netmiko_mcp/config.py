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
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    inventory_type: Literal["netmiko_tools"] = Field(default="netmiko_tools")
    inventory_file: str | None = Field(default=None)
    command_file: str = Field(default="~/commands.yml")
    allow_pipe: bool = Field(default=False)

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
        """
        config_path_str = os.environ.get("NETMIKO_MCP_CONFIG")
        if config_path_str:
            config_path = Path(config_path_str).expanduser()
        else:
            config_path = Path.home() / ".netmiko-mcp.yml"

        # If the YAML file exists, we register it as the lowest priority settings source.
        # This guarantees that environment variables and .env files will always take
        # precedence over any values defined inside the physical YAML file.
        yaml_source = None
        if config_path.is_file():
            yaml_source = YamlConfigSettingsSource(settings_cls, yaml_file=config_path)

        sources = [init_settings, env_settings, dotenv_settings]
        if yaml_source:
            sources.append(yaml_source)

        return tuple(sources)


# The global singleton configuration object loaded at startup
settings = McpConfig()

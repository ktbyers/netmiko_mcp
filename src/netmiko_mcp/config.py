import os
from pathlib import Path
from typing import Literal, Optional, Tuple, Type

from pydantic import Field, model_validator
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
    inventory_file: Optional[str] = Field(default=None)
    command_file: str = Field(default="~/commands.yml")
    allow_pipe: bool = Field(default=False)
    # Characters permitted in commands. The pipe character '|' is intentionally
    # absent — it is added to the effective allowed set automatically when
    # allow_pipe is True. Adding '|' here while allow_pipe is False is an error.
    allowed_command_chars: str = Field(
        default="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ./:_-,"
    )
    pipe_modifiers: list[str] = Field(default=["include", "exclude", "section", "begin", "count"])
    max_workers: int = Field(default=10)
    save_output_dir: str = Field(default="~/.netmiko_mcp_tmp")
    # Output exceeding this line count is automatically saved to save_output_dir
    # instead of being returned inline to the client.
    save_threshold: int = Field(default=1000)

    # Transport
    transport: Literal["stdio", "streamable-http"] = Field(default="stdio")
    http_host: str = Field(default="127.0.0.1")
    http_port: int = Field(default=8000)
    http_path: str = Field(default="/mcp")
    http_auth_enabled: bool = Field(default=True)

    # Audit logging
    audit_log_enabled: bool = Field(default=True)
    audit_log_destination: Literal["file", "syslog", "both"] = Field(default="file")
    audit_log_file: str = Field(default="~/.netmiko_mcp_audit.log")
    audit_log_syslog_address: str = Field(default="/dev/log")
    audit_log_syslog_facility: str = Field(default="local0")
    audit_log_read_transcript: bool = Field(default=False)
    audit_log_transcript_dir: str = Field(default="~/.netmiko_mcp_transcripts")

    @model_validator(mode="after")
    def _check_pipe_char_consistency(self) -> "McpConfig":
        """Raise if '|' appears in allowed_command_chars while allow_pipe is False.
        The pipe character is managed automatically via allow_pipe and must not be
        added to allowed_command_chars directly when pipe support is disabled.
        """
        if "|" in self.allowed_command_chars and not self.allow_pipe:
            raise ValueError(
                "'|' must not appear in allowed_command_chars when allow_pipe is False. "
                "Set allow_pipe: true to enable pipe support."
            )
        return self

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

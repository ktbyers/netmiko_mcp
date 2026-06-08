import os
from pathlib import Path
from typing import Literal, Optional, Tuple, Type

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
    inventory_file: Optional[str] = Field(default=None)
    command_file: str = Field(default="~/commands.yml")
    allow_pipe: bool = Field(default=False)
    unsafe_chars: list[str] = Field(default=[";", "\n", "\r", "&"])
    pipe_modifiers: list[str] = Field(default=["include", "exclude", "section", "begin", "count"])
    max_workers: int = Field(default=10)
    save_output_dir: str = Field(default="~/.netmiko_mcp_tmp")

    # Audit logging
    audit_log_enabled: bool = Field(default=True)
    audit_log_destination: Literal["file", "syslog", "both"] = Field(default="file")
    audit_log_file: str = Field(default="~/.netmiko_mcp_audit.log")
    audit_log_max_bytes: int = Field(default=10_485_760)  # 10 MB
    audit_log_backup_count: int = Field(default=5)
    audit_log_syslog_address: str = Field(default="/dev/log")
    audit_log_syslog_facility: str = Field(default="local0")
    audit_log_read_transcript: bool = Field(default=False)
    audit_log_transcript_dir: str = Field(default="~/.netmiko_mcp_transcripts")
    audit_log_retention_days: int = Field(default=30)

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

from pathlib import Path
import pytest
from pydantic_core import ValidationError

from netmiko_mcp.config import McpConfig


def test_mcp_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that McpConfig loads with the correct default values."""
    # Isolate from any real ~/.netmiko-mcp.yml on the host
    monkeypatch.setenv("NETMIKO_MCP_CONFIG", "/nonexistent/path.yml")
    config = McpConfig()
    assert config.inventory_type == "netmiko_tools"
    assert config.inventory_file is None
    assert config.command_file == "~/commands.yml"
    assert config.allow_pipe is False
    assert config.unsafe_chars == [";", "\n", "\r", "&"]
    assert config.pipe_modifiers == ["include", "exclude", "section", "begin", "count"]
    assert config.max_workers == 10
    assert config.save_output_dir == "~/.netmiko_mcp_tmp"


def test_mcp_config_validation() -> None:
    """Test that McpConfig strictly validates inventory_type."""
    with pytest.raises(ValidationError):
        # Should fail because only 'netmiko_tools' is permitted by the Literal
        McpConfig(inventory_type="invalid_type")  # type: ignore


@pytest.mark.anyio
async def test_mcp_config_default_file_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that McpConfig natively attempts to load from ~/.netmiko-mcp.yml when no env var is set."""
    # Ensure the environment variable is NOT set
    monkeypatch.delenv("NETMIKO_MCP_CONFIG", raising=False)

    # Mock Path.home() to point to our isolated tmp_path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Create the default file in our mocked home directory
    default_cfg = tmp_path / ".netmiko-mcp.yml"
    default_cfg.write_text("allow_pipe: true\n", encoding="utf-8")

    config = McpConfig()
    assert config.allow_pipe is True


@pytest.mark.anyio
async def test_mcp_config_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that McpConfig natively reads from NETMIKO_MCP_ environment variables."""
    # We temporarily set environment variables to test native env reading
    monkeypatch.setenv("NETMIKO_MCP_INVENTORY_TYPE", "netmiko_tools")
    monkeypatch.setenv("NETMIKO_MCP_INVENTORY_FILE", "/env/path.yml")
    monkeypatch.setenv("NETMIKO_MCP_COMMAND_FILE", "/env/commands.yml")
    monkeypatch.setenv("NETMIKO_MCP_ALLOW_PIPE", "true")
    monkeypatch.setenv("NETMIKO_MCP_UNSAFE_CHARS", '[";" , "|", "!"]')
    monkeypatch.setenv("NETMIKO_MCP_PIPE_MODIFIERS", '["include", "exclude", "grep"]')
    monkeypatch.setenv("NETMIKO_MCP_MAX_WORKERS", "20")
    monkeypatch.setenv("NETMIKO_MCP_SAVE_OUTPUT_DIR", "/tmp/mcp_out")

    config = McpConfig()
    assert config.inventory_type == "netmiko_tools"
    assert config.inventory_file == "/env/path.yml"
    assert config.command_file == "/env/commands.yml"
    assert config.allow_pipe is True
    assert config.unsafe_chars == [";", "|", "!"]
    assert config.pipe_modifiers == ["include", "exclude", "grep"]
    assert config.max_workers == 20
    assert config.save_output_dir == "/tmp/mcp_out"


@pytest.mark.anyio
async def test_mcp_config_yaml_max_workers_and_save_output_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that max_workers and save_output_dir set in a config file are respected."""
    cfg_file = tmp_path / "test-config.yml"
    cfg_file.write_text("max_workers: 25\nsave_output_dir: /tmp/custom_out\n", encoding="utf-8")
    monkeypatch.setenv("NETMIKO_MCP_CONFIG", str(cfg_file))

    config = McpConfig()
    assert config.max_workers == 25
    assert config.save_output_dir == "/tmp/custom_out"


@pytest.mark.anyio
async def test_mcp_config_yaml_pipe_modifiers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that pipe_modifiers set in a config file is respected."""
    cfg_file = tmp_path / "test-config.yml"
    cfg_file.write_text(
        'pipe_modifiers: ["include", "exclude", "grep", "json"]\n', encoding="utf-8"
    )
    monkeypatch.setenv("NETMIKO_MCP_CONFIG", str(cfg_file))

    config = McpConfig()
    assert config.pipe_modifiers == ["include", "exclude", "grep", "json"]


@pytest.mark.anyio
async def test_mcp_config_yaml_unsafe_chars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that unsafe_chars set in a config file is respected."""
    cfg_file = tmp_path / "test-config.yml"
    cfg_file.write_text('unsafe_chars: [";", "\\n", "\\r", "&", "|"]\n', encoding="utf-8")
    monkeypatch.setenv("NETMIKO_MCP_CONFIG", str(cfg_file))

    config = McpConfig()
    assert config.unsafe_chars == [";", "\n", "\r", "&", "|"]


@pytest.mark.anyio
async def test_mcp_config_yaml_allow_pipe_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that allow_pipe: false set explicitly in a config file is respected."""
    cfg_file = tmp_path / "test-config.yml"
    cfg_file.write_text("allow_pipe: false\n", encoding="utf-8")
    monkeypatch.setenv("NETMIKO_MCP_CONFIG", str(cfg_file))

    config = McpConfig()
    assert config.allow_pipe is False


@pytest.mark.anyio
async def test_load_config_real_yaml_and_env_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Test loading configuration from a real physical YAML file on disk,
    verifying alias resolution and environment variable precedence.
    """
    # Create a real physical configuration file using the plain lowercase keys
    cfg_file = tmp_path / "test-config.yml"
    cfg_content = """---
inventory_type: "netmiko_tools"
inventory_file: "/yaml/netmiko.yml"
command_file: "/yaml/commands.yml"
allow_pipe: true
"""
    cfg_file.write_text(cfg_content, encoding="utf-8")

    # Point our environment at our temporary configuration file
    monkeypatch.setenv("NETMIKO_MCP_CONFIG", str(cfg_file))

    # Load the configuration and verify Pydantic parsed the plain YAML fields correctly
    config = McpConfig()
    assert config.inventory_type == "netmiko_tools"
    assert config.inventory_file == "/yaml/netmiko.yml"
    assert config.command_file == "/yaml/commands.yml"
    assert config.allow_pipe is True

    # Set environment variables to override the values loaded from the YAML file
    # and prove that environment variables have highest precedence
    monkeypatch.setenv("NETMIKO_MCP_ALLOW_PIPE", "false")
    monkeypatch.setenv("NETMIKO_MCP_COMMAND_FILE", "/env/override_commands.yml")

    config_override = McpConfig()
    assert config_override.allow_pipe is False
    assert config_override.command_file == "/env/override_commands.yml"
    assert config_override.inventory_file == "/yaml/netmiko.yml"


@pytest.mark.anyio
async def test_inventory_type_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Test that NETMIKO_MCP_INVENTORY_TYPE overrides the YAML configuration.
    We prove this by placing an invalid type in the YAML and a valid one in the environment.
    """
    cfg_file = tmp_path / "test-config.yml"
    cfg_file.write_text("inventory_type: invalid_yaml_type\n", encoding="utf-8")
    monkeypatch.setenv("NETMIKO_MCP_CONFIG", str(cfg_file))

    # 1. Prove the invalid YAML fails on its own
    with pytest.raises(ValidationError):
        McpConfig()

    # 2. Prove the environment variable overrides it safely
    monkeypatch.setenv("NETMIKO_MCP_INVENTORY_TYPE", "netmiko_tools")
    config = McpConfig()
    assert config.inventory_type == "netmiko_tools"


def test_mcp_config_audit_log_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Audit log fields should have correct default values."""
    monkeypatch.setenv("NETMIKO_MCP_CONFIG", "/nonexistent/path.yml")
    config = McpConfig()
    assert config.audit_log_enabled is True
    assert config.audit_log_destination == "file"
    assert config.audit_log_file == "~/.netmiko_mcp_audit.log"
    assert config.audit_log_max_bytes == 10_485_760
    assert config.audit_log_backup_count == 5
    assert config.audit_log_syslog_address == "/dev/log"
    assert config.audit_log_syslog_facility == "local0"
    assert config.audit_log_read_transcript is False
    assert config.audit_log_transcript_dir == "~/.netmiko_mcp_transcripts"
    assert config.audit_log_retention_days == 30


@pytest.mark.anyio
async def test_mcp_config_audit_log_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Audit log fields should be overridable via NETMIKO_MCP_AUDIT_LOG_* env vars."""
    monkeypatch.setenv("NETMIKO_MCP_AUDIT_LOG_ENABLED", "false")
    monkeypatch.setenv("NETMIKO_MCP_AUDIT_LOG_DESTINATION", "syslog")
    monkeypatch.setenv("NETMIKO_MCP_AUDIT_LOG_FILE", "/var/log/mcp_audit.log")
    monkeypatch.setenv("NETMIKO_MCP_AUDIT_LOG_MAX_BYTES", "5242880")
    monkeypatch.setenv("NETMIKO_MCP_AUDIT_LOG_BACKUP_COUNT", "10")
    monkeypatch.setenv("NETMIKO_MCP_AUDIT_LOG_SYSLOG_ADDRESS", "192.168.1.1:514")
    monkeypatch.setenv("NETMIKO_MCP_AUDIT_LOG_SYSLOG_FACILITY", "local1")
    monkeypatch.setenv("NETMIKO_MCP_AUDIT_LOG_READ_TRANSCRIPT", "true")
    monkeypatch.setenv("NETMIKO_MCP_AUDIT_LOG_TRANSCRIPT_DIR", "/tmp/transcripts")
    monkeypatch.setenv("NETMIKO_MCP_AUDIT_LOG_RETENTION_DAYS", "7")

    config = McpConfig()
    assert config.audit_log_enabled is False
    assert config.audit_log_destination == "syslog"
    assert config.audit_log_file == "/var/log/mcp_audit.log"
    assert config.audit_log_max_bytes == 5_242_880
    assert config.audit_log_backup_count == 10
    assert config.audit_log_syslog_address == "192.168.1.1:514"
    assert config.audit_log_syslog_facility == "local1"
    assert config.audit_log_read_transcript is True
    assert config.audit_log_transcript_dir == "/tmp/transcripts"
    assert config.audit_log_retention_days == 7


@pytest.mark.anyio
async def test_mcp_config_audit_log_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Audit log fields should be configurable from the YAML config file."""
    cfg_file = tmp_path / "test-config.yml"
    cfg_file.write_text(
        "audit_log_enabled: false\naudit_log_destination: both\naudit_log_retention_days: 90\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NETMIKO_MCP_CONFIG", str(cfg_file))
    config = McpConfig()
    assert config.audit_log_enabled is False
    assert config.audit_log_destination == "both"
    assert config.audit_log_retention_days == 90

"""
Tests for the HTTP transport wiring in server.py.

These tests verify startup validation, the _run_http() plumbing, and the main()
dispatch logic for streamable-http mode. The uvicorn.run call is mocked throughout
so no real network listener is started.
"""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from netmiko_mcp.server import _get_bearer_token, _run_http, _validate_startup, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_commands_file(tmp_path: Path) -> Path:
    """Write a minimal commands.yml and return its path."""
    cmd_file = tmp_path / "commands.yml"
    cmd_file.write_text("allowed_commands: []\n", encoding="utf-8")
    return cmd_file


# ---------------------------------------------------------------------------
# _get_bearer_token
# ---------------------------------------------------------------------------


def test_get_bearer_token_returns_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """_get_bearer_token should return the value of NETMIKO_MCP_HTTP_BEARER_TOKEN."""
    monkeypatch.setenv("NETMIKO_MCP_HTTP_BEARER_TOKEN", "my-secret")
    assert _get_bearer_token() == "my-secret"


def test_get_bearer_token_strips_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    """_get_bearer_token should strip leading/trailing whitespace from the env value."""
    monkeypatch.setenv("NETMIKO_MCP_HTTP_BEARER_TOKEN", "  my-secret  ")
    assert _get_bearer_token() == "my-secret"


def test_get_bearer_token_raises_if_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """_get_bearer_token should raise SystemExit when the env var is not set."""
    monkeypatch.delenv("NETMIKO_MCP_HTTP_BEARER_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="NETMIKO_MCP_HTTP_BEARER_TOKEN"):
        _get_bearer_token()


def test_get_bearer_token_raises_if_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """_get_bearer_token should raise SystemExit when the env var is set but empty."""
    monkeypatch.setenv("NETMIKO_MCP_HTTP_BEARER_TOKEN", "")
    with pytest.raises(SystemExit, match="NETMIKO_MCP_HTTP_BEARER_TOKEN"):
        _get_bearer_token()


# ---------------------------------------------------------------------------
# _validate_startup — HTTP transport checks
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.server.settings")
def test_validate_startup_http_mode_requires_bearer_token(
    mock_settings: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In streamable-http mode with auth enabled, startup should fail if bearer token is absent."""
    cmd_file = _write_commands_file(tmp_path)
    mock_settings.command_file = str(cmd_file)
    mock_settings.transport = "streamable-http"
    mock_settings.http_auth_enabled = True
    monkeypatch.delenv("NETMIKO_MCP_HTTP_BEARER_TOKEN", raising=False)

    with pytest.raises(SystemExit, match="NETMIKO_MCP_HTTP_BEARER_TOKEN"):
        _validate_startup()


@patch("netmiko_mcp.server.settings")
def test_validate_startup_http_mode_auth_disabled_no_token_required(
    mock_settings: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In streamable-http mode with auth disabled, no bearer token check should occur."""
    cmd_file = _write_commands_file(tmp_path)
    mock_settings.command_file = str(cmd_file)
    mock_settings.transport = "streamable-http"
    mock_settings.http_auth_enabled = False
    monkeypatch.delenv("NETMIKO_MCP_HTTP_BEARER_TOKEN", raising=False)

    _validate_startup()  # should not raise


@patch("netmiko_mcp.server.settings")
def test_validate_startup_http_mode_with_valid_token_succeeds(
    mock_settings: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In streamable-http mode with auth enabled and token set, startup should succeed."""
    cmd_file = _write_commands_file(tmp_path)
    mock_settings.command_file = str(cmd_file)
    mock_settings.transport = "streamable-http"
    mock_settings.http_auth_enabled = True
    monkeypatch.setenv("NETMIKO_MCP_HTTP_BEARER_TOKEN", "valid-token")

    _validate_startup()  # should not raise


@patch("netmiko_mcp.server.settings")
def test_validate_startup_stdio_mode_ignores_bearer_token(
    mock_settings: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In stdio mode, the bearer token check should not run even if auth_enabled is True."""
    cmd_file = _write_commands_file(tmp_path)
    mock_settings.command_file = str(cmd_file)
    mock_settings.transport = "stdio"
    mock_settings.http_auth_enabled = True
    monkeypatch.delenv("NETMIKO_MCP_HTTP_BEARER_TOKEN", raising=False)

    _validate_startup()  # should not raise


# ---------------------------------------------------------------------------
# _run_http
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.server.uvicorn.run")
@patch("netmiko_mcp.server.settings")
def test_run_http_calls_uvicorn_with_configured_host_port(
    mock_settings: Any, mock_uvicorn_run: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_run_http should pass http_host and http_port to uvicorn.run."""
    mock_settings.http_host = "127.0.0.1"
    mock_settings.http_port = 9000
    mock_settings.http_path = "/mcp"
    mock_settings.http_auth_enabled = False
    monkeypatch.delenv("NETMIKO_MCP_HTTP_BEARER_TOKEN", raising=False)

    _run_http()

    mock_uvicorn_run.assert_called_once()
    _, kwargs = mock_uvicorn_run.call_args
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 9000


@patch("netmiko_mcp.server.uvicorn.run")
@patch("netmiko_mcp.server.settings")
def test_run_http_wraps_app_with_auth_middleware_when_enabled(
    mock_settings: Any, mock_uvicorn_run: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When http_auth_enabled is True, the ASGI app passed to uvicorn should be a BearerTokenMiddleware."""
    from netmiko_mcp.http_auth import BearerTokenMiddleware

    mock_settings.http_host = "127.0.0.1"
    mock_settings.http_port = 8000
    mock_settings.http_path = "/mcp"
    mock_settings.http_auth_enabled = True
    monkeypatch.setenv("NETMIKO_MCP_HTTP_BEARER_TOKEN", "secret")

    _run_http()

    mock_uvicorn_run.assert_called_once()
    app_arg = mock_uvicorn_run.call_args[0][0]
    assert isinstance(app_arg, BearerTokenMiddleware)


@patch("netmiko_mcp.server.uvicorn.run")
@patch("netmiko_mcp.server.settings")
def test_run_http_no_auth_middleware_when_disabled(
    mock_settings: Any, mock_uvicorn_run: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When http_auth_enabled is False, the ASGI app passed to uvicorn should not be wrapped."""
    from netmiko_mcp.http_auth import BearerTokenMiddleware

    mock_settings.http_host = "127.0.0.1"
    mock_settings.http_port = 8000
    mock_settings.http_path = "/mcp"
    mock_settings.http_auth_enabled = False
    monkeypatch.delenv("NETMIKO_MCP_HTTP_BEARER_TOKEN", raising=False)

    _run_http()

    mock_uvicorn_run.assert_called_once()
    app_arg = mock_uvicorn_run.call_args[0][0]
    assert not isinstance(app_arg, BearerTokenMiddleware)


# ---------------------------------------------------------------------------
# main() dispatch
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.server.configure_audit_logger")
@patch("netmiko_mcp.server._run_http")
@patch("netmiko_mcp.server.settings")
def test_main_dispatches_to_run_http_when_transport_is_streamable_http(
    mock_settings: Any,
    mock_run_http: Any,
    mock_configure: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main() should call _run_http() when transport is 'streamable-http'."""
    cmd_file = _write_commands_file(tmp_path)
    mock_settings.command_file = str(cmd_file)
    mock_settings.transport = "streamable-http"
    mock_settings.http_auth_enabled = False

    main()

    mock_run_http.assert_called_once()


@patch("netmiko_mcp.server.configure_audit_logger")
@patch("netmiko_mcp.server.mcp")
@patch("netmiko_mcp.server.settings")
def test_main_dispatches_to_stdio_when_transport_is_stdio(
    mock_settings: Any,
    mock_mcp: Any,
    mock_configure: Any,
    tmp_path: Path,
) -> None:
    """main() should call mcp.run(transport='stdio') when transport is 'stdio'."""
    cmd_file = _write_commands_file(tmp_path)
    mock_settings.command_file = str(cmd_file)
    mock_settings.transport = "stdio"
    mock_settings.http_auth_enabled = False

    main()

    mock_mcp.run.assert_called_once_with(transport="stdio")

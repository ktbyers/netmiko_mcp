import functools
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.types import ASGIApp

from netmiko_mcp.audit import configure_audit_logger, log_tool_invocation
from netmiko_mcp.config import settings
from netmiko_mcp.connection import (
    list_device_outputs as _list_device_outputs,
    read_device_output as _read_device_output,
    run_show_command,
    run_show_command_on_group,
)
from netmiko_mcp.http_auth import BearerTokenMiddleware
from netmiko_mcp.inventory import get_group_names, get_sanitized_inventory
from netmiko_mcp.security import validate_command_lists

# Set once by _validate_startup() for stdio startup failures. All tools return
# it immediately via @check_startup_error so errors surface in-session.
_startup_error: str | None = None

_F = TypeVar("_F", bound=Callable[..., Any])


def check_startup_error(func: _F) -> _F:
    """Decorator that short-circuits a tool and returns _startup_error if set.

    Apply below @mcp.tool() on every tool so that a misconfigured server
    surfaces a clear error through any tool call rather than silently
    misbehaving. functools.wraps preserves the original function metadata
    so FastMCP generates the correct tool schema.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if _startup_error:
            return _startup_error
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


# Initialize the FastMCP server. The HTTP settings (host, port, path) are passed
# here so that streamable_http_app() uses the operator-configured values when the
# HTTP transport is selected. They have no effect in stdio mode.
mcp = FastMCP(
    "netmiko-mcp",
    instructions="MCP Server for Netmiko Network Automation",
    host=settings.http_host,
    port=settings.http_port,
    streamable_http_path=settings.http_path,
)


@mcp.tool()
@check_startup_error
def list_groups() -> str:
    """
    List all device groups defined in the inventory.
    Returns a JSON-encoded list of group name strings.
    """
    log_tool_invocation(tool="list_groups", arguments={})
    try:
        return json.dumps(get_group_names())
    except ValueError as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@check_startup_error
def list_devices(device_or_group: str = "all") -> str:
    """
    List devices from the Netmiko inventory.
    You can query by 'all' (default), a specific 'group-name', or a 'device-name'.
    Returns a JSON string containing device configurations (excluding credentials).
    """
    log_tool_invocation(tool="list_devices", arguments={"device_or_group": device_or_group})
    return get_sanitized_inventory(device_or_group)


@mcp.tool()
@check_startup_error
def send_show_command(
    device_name: str,
    command: str,
    use_textfsm: bool = False,
    save_output: bool = False,
) -> str | list[Any] | dict[str, Any]:
    """
    Connect to a network device and execute a show command.

    Args:
        device_name: The exact name of the device from the inventory.
        command: The CLI command to execute (e.g. 'show ip int brief').
        use_textfsm: Set to True to attempt parsing the output into structured JSON data using ntc-templates.
        save_output: If True, always save output to disk and return the filename instead
                     of the raw output. Useful when you intend to refer back to the output
                     multiple times without re-running the command.

    If save_output is False and the output exceeds the configured save_threshold
    (default 1000 lines) it is automatically saved to disk and a short notification
    is returned instead. Use list_device_outputs and read_device_output to retrieve
    the saved content.
    """
    return run_show_command(device_name, command, use_textfsm, save_output)


@mcp.tool()
@check_startup_error
def send_show_command_to_group(
    device_or_group: str,
    command: str,
    use_textfsm: bool = False,
    save_output: bool = False,
) -> dict[str, Any]:
    """
    Connect to a group of devices concurrently and execute a show command on each.

    Args:
        device_or_group: A device group name or device name from the inventory.
        command: The CLI command to execute on all devices (e.g. 'show version').
        use_textfsm: If True, attempt to return parsed structured JSON data.
        save_output: If True, save per-device output to files and return file paths
                     instead of raw output.

    Returns:
        A dict mapping each device name to its output (or saved file path).
    """
    return run_show_command_on_group(device_or_group, command, use_textfsm, save_output)


@mcp.tool()
@check_startup_error
def list_device_outputs(device_or_group: str) -> dict[str, Any]:
    """
    List saved output files for a device, group, or all devices.

    Args:
        device_or_group: A device name, group name, or 'all'.

    Returns:
        A dict mapping each device name to a list of saved filenames (newest first).
        Devices with no saved output are included with an empty list.
    """
    log_tool_invocation(tool="list_device_outputs", arguments={"device_or_group": device_or_group})
    return _list_device_outputs(device_or_group)


@mcp.tool()
@check_startup_error
def read_device_output(
    device_name: str,
    filename: str,
    offset: int = 0,
    limit: int = 500,
) -> str:
    """
    Read a previously saved output file for a specific device, with pagination.

    Args:
        device_name: The device name whose output directory to read from.
        filename: The exact filename as returned by list_device_outputs.
        offset: Line number to start reading from (0-indexed). Defaults to 0.
        limit: Maximum number of lines to return per call. Defaults to 500.

    The response header shows the line range and total line count. If more lines
    remain, a continuation hint tells you which offset to use on the next call.
    """
    log_tool_invocation(
        tool="read_device_output",
        arguments={
            "device_name": device_name,
            "filename": filename,
            "offset": offset,
            "limit": limit,
        },
    )
    return _read_device_output(device_name, filename, offset, limit)


@mcp.tool()
@check_startup_error
def ping() -> str:
    """A simple health check tool to verify the MCP server is responding."""
    log_tool_invocation(tool="ping", arguments={})
    return "pong"


def _get_bearer_token() -> str:
    """Retrieve the HTTP bearer token from the environment.

    The token is read from NETMIKO_MCP_HTTP_BEARER_TOKEN. It is intentionally not a
    pydantic-settings field so it cannot be stored in the YAML config file — secrets
    belong in the environment only.

    Raises SystemExit if the variable is not set or is empty.
    """
    token = os.environ.get("NETMIKO_MCP_HTTP_BEARER_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "Startup Error: NETMIKO_MCP_HTTP_BEARER_TOKEN must be set as an environment "
            "variable when running in streamable-http mode with http_auth_enabled: true."
        )
    return token


def _validate_startup() -> str | None:
    """Validate required configuration before starting the server.

    For the streamable-http transport, raises SystemExit if NETMIKO_MCP_CONFIG
    points at a missing file, if command_file does not exist, or if
    NETMIKO_MCP_HTTP_BEARER_TOKEN is not set — all errors are visible to the
    operator in the terminal where the server is started manually.

    For the stdio transport, returns an error string for the same file-missing
    conditions so the caller can surface it in-session rather than raising before
    the MCP handshake.
    Returns None when all checks pass.
    """
    config_path_str = os.environ.get("NETMIKO_MCP_CONFIG")
    if config_path_str:
        config_path = Path(config_path_str).expanduser()
        if not config_path.is_file():
            error_msg = (
                f"Startup Error: NETMIKO_MCP_CONFIG is set to '{config_path_str}' "
                f"but that file does not exist."
            )
            if settings.transport == "streamable-http":
                raise SystemExit(error_msg)
            else:
                return error_msg

    command_file = Path(settings.command_file).expanduser()
    if not command_file.is_file():
        if settings.transport == "streamable-http":
            raise SystemExit(
                f"Startup Error: command_file '{settings.command_file}' does not exist. "
                f"Create this file with your allowed_commands before starting the server."
            )
        else:
            return (
                f"Startup Error: command_file '{settings.command_file}' does not exist. "
                f"Create this file with your allowed_commands before starting the server."
            )

    from netmiko.utilities import load_yaml_file

    commands = load_yaml_file(str(command_file))
    allowed_commands = commands.get("allowed_commands", [])
    denied_commands = commands.get("denied_commands", [])
    errors = validate_command_lists(
        allowed_commands=allowed_commands,
        denied_commands=denied_commands,
    )
    if errors:
        error_msg = "Startup Error: " + " ".join(errors)
        if settings.transport == "streamable-http":
            raise SystemExit(error_msg)
        else:
            return error_msg

    if settings.transport == "streamable-http" and settings.http_auth_enabled:
        _get_bearer_token()
    return None


def _run_http() -> None:
    """Start the MCP server using the Streamable HTTP transport.

    Retrieves the ASGI application from FastMCP, optionally wraps it with RFC 6750
    bearer token authentication middleware, and hands it to uvicorn.

    TLS termination is intentionally left to a reverse proxy. Running uvicorn
    with raw TLS in application code is possible but adds certificate lifecycle
    management complexity that a proxy (nginx, Caddy, etc.) handles better.
    """
    app: ASGIApp = mcp.streamable_http_app()

    if settings.http_auth_enabled:
        token = _get_bearer_token()
        app = BearerTokenMiddleware(app, token)

    uvicorn.run(app, host=settings.http_host, port=settings.http_port)


def main() -> None:
    """Entry point for the Netmiko MCP server."""
    global _startup_error
    _startup_error = _validate_startup()
    configure_audit_logger()
    if settings.transport == "streamable-http":
        _run_http()
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

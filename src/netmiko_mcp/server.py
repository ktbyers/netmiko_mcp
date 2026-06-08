from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from netmiko_mcp.audit import configure_audit_logger, log_tool_invocation
from netmiko_mcp.config import settings
from netmiko_mcp.connection import (
    list_device_outputs as _list_device_outputs,
    read_device_output as _read_device_output,
    run_show_command,
    run_show_command_on_group,
)
from netmiko_mcp.inventory import get_sanitized_inventory

# Initialize the FastMCP server
mcp = FastMCP("netmiko-mcp", instructions="MCP Server for Netmiko Network Automation")


@mcp.tool()
def list_devices(device_or_group: str = "all") -> str:
    """
    List devices from the Netmiko inventory.
    You can query by 'all' (default), a specific 'group-name', or a 'device-name'.
    Returns a JSON string containing device configurations (excluding credentials).
    """
    log_tool_invocation(tool="list_devices", arguments={"device_or_group": device_or_group})
    return get_sanitized_inventory(device_or_group)


@mcp.tool()
def send_show_command(
    device_name: str, command: str, use_textfsm: bool = False
) -> str | list[Any] | dict[str, Any]:
    """
    Connect to a network device and execute a show command.

    Args:
        device_name: The exact name of the device from the inventory.
        command: The CLI command to execute (e.g. 'show ip int brief').
        use_textfsm: Set to True to attempt parsing the output into structured JSON data using ntc-templates.
    """
    return run_show_command(device_name, command, use_textfsm)


@mcp.tool()
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
def read_device_output(device_name: str, filename: str) -> str:
    """
    Read a previously saved output file for a specific device.

    Args:
        device_name: The device name whose output directory to read from.
        filename: The exact filename as returned by list_device_outputs.

    Returns:
        The file content as a string, or an error message.
    """
    log_tool_invocation(
        tool="read_device_output",
        arguments={"device_name": device_name, "filename": filename},
    )
    return _read_device_output(device_name, filename)


@mcp.tool()
def ping() -> str:
    """A simple health check tool to verify the MCP server is responding."""
    log_tool_invocation(tool="ping", arguments={})
    return "pong"


def _validate_startup() -> None:
    """Validate required configuration before starting the server.

    Raises SystemExit with a clear message if the command_file does not exist,
    preventing the server from running in a state where all commands are silently denied.
    """
    command_file = Path(settings.command_file).expanduser()
    if not command_file.is_file():
        raise SystemExit(
            f"Startup Error: command_file '{settings.command_file}' does not exist. "
            f"Create this file with your allowed_commands before starting the server."
        )


def main() -> None:
    """Entry point for the Netmiko MCP server."""
    _validate_startup()
    configure_audit_logger()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

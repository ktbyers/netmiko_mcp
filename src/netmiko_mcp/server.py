from typing import Any

from mcp.server.fastmcp import FastMCP

from netmiko_mcp.connection import run_show_command
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
def ping() -> str:
    """A simple health check tool to verify the MCP server is responding."""
    return "pong"


def main() -> None:
    """Entry point for the Netmiko MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

import json
from typing import Any, Dict

from mcp.server.fastmcp import FastMCP
from netmiko.cli_tools.helpers import obtain_devices

# Initialize the FastMCP server
mcp = FastMCP("netmiko-mcp", instructions="MCP Server for Netmiko Network Automation")


def get_device_params(device_name: str) -> Dict[str, Any]:
    """
    Retrieve full device parameters including credentials.
    INTERNAL USE ONLY. Never expose this directly to the LLM.
    """
    devices = obtain_devices(device_name)
    if isinstance(devices, str):
        # Netmiko returns a string error message if the device/group is not found
        raise ValueError(devices)
    if device_name not in devices:
        raise ValueError(f"Device '{device_name}' not found in inventory.")
    return devices[device_name]


def get_sanitized_inventory(device_or_group: str) -> str:
    """
    Retrieve device inventory by group-name, all, or device-name.
    Returns JSON string with sensitive credentials completely removed.
    """
    devices = obtain_devices(device_or_group)
    if isinstance(devices, str):
        # Return the error as structured JSON
        return json.dumps({"error": devices})

    sanitized_devices = {}
    for name, params in devices.items():
        # Ensure we NEVER leak credentials
        safe_params = {
            k: v for k, v in params.items() if k not in ("username", "password", "secret")
        }
        sanitized_devices[name] = safe_params

    return json.dumps(sanitized_devices, indent=2)


@mcp.tool()
def list_devices(device_or_group: str = "all") -> str:
    """
    List devices from the Netmiko inventory.
    You can query by 'all' (default), a specific 'group-name', or a 'device-name'.
    Returns a JSON string containing device configurations (excluding credentials).
    """
    return get_sanitized_inventory(device_or_group)


@mcp.tool()
def ping() -> str:
    """A simple health check tool to verify the MCP server is responding."""
    return "pong"


def main() -> None:
    """Entry point for the Netmiko MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

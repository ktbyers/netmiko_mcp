from mcp.server.fastmcp import FastMCP

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
def ping() -> str:
    """A simple health check tool to verify the MCP server is responding."""
    return "pong"


def main() -> None:
    """Entry point for the Netmiko MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

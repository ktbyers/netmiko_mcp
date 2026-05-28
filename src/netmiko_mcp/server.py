from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server
mcp = FastMCP("netmiko-mcp", instructions="MCP Server for Netmiko Network Automation")


@mcp.tool()
def ping() -> str:
    """A simple health check tool to verify the MCP server is responding."""
    return "pong"


def main() -> None:
    """Entry point for the Netmiko MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

import json

from netmiko import ConnectHandler
from netmiko.exceptions import (
    NetmikoAuthenticationException,
    NetmikoTimeoutException,
)

from netmiko_mcp.inventory import get_device_params
from netmiko_mcp.security import validate_command


def run_show_command(device_name: str, command: str, use_textfsm: bool = False) -> str:
    """
    Connect to a network device and execute a single show command.

    Args:
        device_name: The name of the device in the inventory.
        command: The CLI command to execute.
        use_textfsm: If True, attempt to return parsed JSON data instead of raw text.

    Returns:
        The text output of the command (or JSON string if parsed), or an error message if the connection fails.
    """
    # Security Check
    if not validate_command(command):
        return f"Security Error: Command '{command}' is not permitted."

    # Fetch device parameters
    try:
        params = get_device_params(device_name)
    except ValueError as e:
        return f"Inventory Error: {str(e)}"

    # Establish connection and execute command
    try:
        with ConnectHandler(**params) as net_connect:
            output = net_connect.send_command(command, use_textfsm=use_textfsm)

            # If use_textfsm successfully parsed it, it returns a List or Dict.
            # We must serialize it back to a JSON string for the MCP client.
            if isinstance(output, (list, dict)):
                return json.dumps(output, indent=2)

            return str(output)

    except NetmikoAuthenticationException:
        return f"Connection Error: Authentication failed for device '{device_name}'."
    except NetmikoTimeoutException:
        return f"Connection Error: Connection to device '{device_name}' timed out."
    except Exception as e:
        return f"Execution Error: An unexpected error occurred: {str(e)}"

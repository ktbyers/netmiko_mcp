from netmiko import ConnectHandler
from netmiko.exceptions import (
    NetmikoAuthenticationException,
    NetmikoTimeoutException,
)

from netmiko_mcp.inventory import get_device_params


def run_show_command(device_name: str, command: str) -> str:
    """
    Connect to a device and execute a single show command.

    Args:
        device_name: The name of the device in the inventory.
        command: The CLI command to execute.

    Returns:
        The text output of the command, or an error message if the connection fails.
    """
    try:
        # 1. Fetch secure parameters
        params = get_device_params(device_name)

        # 2. Establish connection
        with ConnectHandler(**params) as net_connect:
            # 3. Execute command and return
            output = net_connect.send_command(command)
            return str(output)

    except ValueError as e:
        # Caught from get_device_params (device not found)
        return f"Inventory Error: {str(e)}"
    except NetmikoAuthenticationException:
        return f"Connection Error: Authentication failed for device '{device_name}'."
    except NetmikoTimeoutException:
        return f"Connection Error: Connection to device '{device_name}' timed out."
    except Exception as e:
        return f"Execution Error: An unexpected error occurred: {str(e)}"

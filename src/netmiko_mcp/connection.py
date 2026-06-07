import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from netmiko import ConnectHandler
from netmiko.exceptions import (
    NetmikoAuthenticationException,
    NetmikoTimeoutException,
)

from netmiko_mcp.config import settings
from netmiko_mcp.inventory import get_device_names, get_device_params
from netmiko_mcp.security import validate_command


def run_show_command(
    device_name: str, command: str, use_textfsm: bool = False
) -> str | list[Any] | dict[str, Any]:
    """
    Connect to a network device and execute a single show command.

    Args:
        device_name: The name of the device in the inventory.
        command: The CLI command to execute.
        use_textfsm: If True, attempt to return parsed JSON data instead of raw text.

    Returns:
        The text output of the command (or structured data if parsed), or an error message if the connection fails.
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
            # We return this directly so the MCP framework can serialize it properly
            # without causing double JSON serialization.
            if isinstance(output, (list, dict)):
                return output

            return str(output)

    except NetmikoAuthenticationException:
        return f"Connection Error: Authentication failed for device '{device_name}'."
    except NetmikoTimeoutException:
        return f"Connection Error: Connection to device '{device_name}' timed out."
    except Exception as e:
        return f"Execution Error: An unexpected error occurred: {str(e)}"


def _sanitize_command_for_filename(command: str) -> str:
    """Convert a command string into a safe filename component.
    Normalizes whitespace and replaces non-alphanumeric characters with underscores.
    Truncated to 50 characters to keep filenames manageable.
    """
    normalized = "_".join(command.split())
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in normalized)
    return safe[:50]


def _save_device_output(device_name: str, command: str, output: Any) -> str:
    """Save command output to a per-device file and return the absolute file path."""
    device_dir = Path(settings.save_output_dir).expanduser() / device_name
    device_dir.mkdir(parents=True, exist_ok=True)
    cmd_name = _sanitize_command_for_filename(command)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = device_dir / f"{cmd_name}_{timestamp}.txt"
    content = json.dumps(output, indent=2) if isinstance(output, (list, dict)) else str(output)
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)


def run_show_command_on_group(
    device_or_group: str,
    command: str,
    use_textfsm: bool = False,
    save_output: bool = False,
) -> dict[str, Any]:
    """
    Execute a show command on a group of devices concurrently using threading.

    The command is validated once before any connections are made. If the command
    is not permitted, a security error is returned immediately without connecting
    to any device.

    Args:
        device_or_group: A device name or group name from the inventory.
        command: The CLI command to execute on all devices.
        use_textfsm: If True, attempt to return parsed structured JSON data.
        save_output: If True, save per-device output to files under save_output_dir
                     and return file paths instead of raw output.

    Returns:
        A dict mapping each device name to its output (or saved file path).
    """
    if not validate_command(command):
        return {"error": f"Security Error: Command '{command}' is not permitted."}

    try:
        device_names = get_device_names(device_or_group)
    except ValueError as e:
        return {"error": f"Inventory Error: {str(e)}"}

    results: dict[str, Any] = {}

    with ThreadPoolExecutor(max_workers=settings.max_workers) as executor:
        future_to_device = {
            executor.submit(run_show_command, name, command, use_textfsm): name
            for name in device_names
        }
        for future in as_completed(future_to_device):
            device_name = future_to_device[future]
            try:
                output = future.result()
                if save_output:
                    results[device_name] = (
                        f"Saved to: {_save_device_output(device_name, command, output)}"
                    )
                else:
                    results[device_name] = output
            except Exception as e:
                results[device_name] = f"Execution Error: {str(e)}"

    return results

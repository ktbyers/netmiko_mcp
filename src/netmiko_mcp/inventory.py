import json
from typing import Any, Dict

from netmiko.cli_tools.helpers import obtain_devices


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

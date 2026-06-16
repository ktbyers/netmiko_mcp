import json
from typing import Any, Dict

import os
from pathlib import Path

from netmiko.cli_tools.helpers import obtain_devices
from netmiko.utilities import find_cfg_file, load_yaml_file

from netmiko_mcp.config import settings


def _set_inventory_env_var() -> None:
    """
    Ensure Netmiko's obtain_devices function reads the correct inventory file
    as defined by our global settings. If inventory_file is explicitly set,
    we override NETMIKO_TOOLS_CFG. Otherwise, we leave it alone so Netmiko
    can follow its native search path.
    """
    if settings.inventory_type == "netmiko_tools" and settings.inventory_file:
        inventory_path = Path(settings.inventory_file).expanduser()
        os.environ["NETMIKO_TOOLS_CFG"] = str(inventory_path)


def get_group_names() -> list[str]:
    """
    Return a list of group names defined in the inventory file.

    Groups are top-level keys whose values are lists of device names.
    Device entries (dict values) and the __meta__ block are excluded.
    Raises ValueError if the inventory file cannot be found.
    """
    _set_inventory_env_var()
    try:
        cfg_file = find_cfg_file()
    except ValueError as e:
        raise ValueError(f"Inventory file not found: {e}") from e
    raw = load_yaml_file(cfg_file)
    return [k for k, v in raw.items() if isinstance(v, list) and k != "__meta__"]


def get_device_params(device_name: str) -> Dict[str, Any]:
    """
    Retrieve full device parameters including credentials.
    INTERNAL USE ONLY. Never expose this directly to the LLM.
    """
    _set_inventory_env_var()
    devices = obtain_devices(device_name)
    if isinstance(devices, str):
        # Netmiko returns a string error message if the device/group is not found
        raise ValueError(devices)
    if device_name not in devices:
        raise ValueError(f"Device '{device_name}' not found in inventory.")
    return devices[device_name]


def get_device_names(device_or_group: str) -> list[str]:
    """
    Return a list of device names for a device or group from the inventory.
    Raises ValueError if the device or group is not found.
    """
    _set_inventory_env_var()
    devices = obtain_devices(device_or_group)
    if isinstance(devices, str):
        raise ValueError(devices)
    return list(devices.keys())


def get_all_device_params(device_or_group: str) -> Dict[str, Any]:
    """
    Retrieve full device parameters for all devices in a group with a single
    obtain_devices call. Avoids repeated inventory decryption when connecting
    to multiple devices concurrently.
    INTERNAL USE ONLY. Never expose this directly to the LLM.
    """
    _set_inventory_env_var()
    devices = obtain_devices(device_or_group)
    if isinstance(devices, str):
        raise ValueError(devices)
    return devices


def get_sanitized_inventory(device_or_group: str) -> str:
    """
    Retrieve device inventory by group-name, all, or device-name.
    Returns JSON string with sensitive credentials completely removed.
    """
    _set_inventory_env_var()
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

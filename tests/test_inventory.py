import os
import json
from typing import Any
from unittest.mock import patch
import pytest

from netmiko_mcp.inventory import (
    get_device_names,
    get_device_params,
    get_group_names,
    get_sanitized_inventory,
)


@patch("netmiko_mcp.inventory.load_yaml_file")
@patch("netmiko_mcp.inventory.find_cfg_file")
def test_get_group_names_returns_groups(mock_find_cfg: Any, mock_load_yaml: Any) -> None:
    """Groups (list values) are returned; device entries (dict values) and __meta__ are excluded."""
    mock_find_cfg.return_value = "/fake/.netmiko.yml"
    mock_load_yaml.return_value = {
        "__meta__": {"encryption": True},
        "cisco1": {"device_type": "cisco_ios", "host": "1.1.1.1"},
        "cisco2": {"device_type": "cisco_ios", "host": "2.2.2.2"},
        "cisco": ["cisco1", "cisco2"],
        "arista": ["arista1"],
    }
    result = get_group_names()
    assert sorted(result) == ["arista", "cisco"]


@patch("netmiko_mcp.inventory.load_yaml_file")
@patch("netmiko_mcp.inventory.find_cfg_file")
def test_get_group_names_no_groups_returns_empty_list(
    mock_find_cfg: Any, mock_load_yaml: Any
) -> None:
    """Inventory with only device entries and __meta__ returns an empty list."""
    mock_find_cfg.return_value = "/fake/.netmiko.yml"
    mock_load_yaml.return_value = {
        "__meta__": {"encryption": False},
        "cisco1": {"device_type": "cisco_ios", "host": "1.1.1.1"},
    }
    result = get_group_names()
    assert result == []


@patch("netmiko_mcp.inventory.load_yaml_file")
@patch("netmiko_mcp.inventory.find_cfg_file")
def test_get_group_names_empty_inventory(mock_find_cfg: Any, mock_load_yaml: Any) -> None:
    """Empty inventory returns an empty list without error."""
    mock_find_cfg.return_value = "/fake/.netmiko.yml"
    mock_load_yaml.return_value = {}
    result = get_group_names()
    assert result == []


@patch("netmiko_mcp.inventory.find_cfg_file")
def test_get_group_names_inventory_not_found(mock_find_cfg: Any) -> None:
    """ValueError from find_cfg_file propagates as a ValueError."""
    mock_find_cfg.side_effect = ValueError("No inventory file found")
    with pytest.raises(ValueError, match="Inventory file not found"):
        get_group_names()


@patch("netmiko_mcp.inventory.obtain_devices")
def test_get_device_params_success(mock_obtain: Any) -> None:
    """Test that get_device_params returns the raw device dictionary."""
    mock_obtain.return_value = {"rtr1": {"host": "1.1.1.1", "username": "admin", "password": "pwd"}}
    result = get_device_params("rtr1")
    assert result["host"] == "1.1.1.1"
    assert result["password"] == "pwd"


@patch("netmiko_mcp.inventory.obtain_devices")
def test_get_device_params_not_found(mock_obtain: Any) -> None:
    """Test that get_device_params raises an error if the device isn't in the returned dict."""
    mock_obtain.return_value = {"rtr2": {"host": "2.2.2.2"}}

    with pytest.raises(ValueError, match="not found in inventory"):
        get_device_params("rtr1")


@patch("netmiko_mcp.inventory.obtain_devices")
def test_get_device_params_error_string(mock_obtain: Any) -> None:
    """Test that get_device_params raises an error if Netmiko returns an error string."""
    mock_obtain.return_value = "Error reading from netmiko devices file."

    with pytest.raises(ValueError, match="Error reading"):
        get_device_params("rtr1")


@patch("netmiko_mcp.inventory.obtain_devices")
def test_get_sanitized_inventory_sanitizes_credentials(mock_obtain: Any) -> None:
    """Test that get_sanitized_inventory strips username, password, and secret from the output."""
    mock_obtain.return_value = {
        "rtr1": {
            "host": "1.1.1.1",
            "device_type": "cisco_ios",
            "username": "admin",
            "password": "pwd",
            "secret": "enable_pwd",
            "port": 22,
        },
        "rtr2": {
            "host": "2.2.2.2",
            "password": "pwd",
        },
    }

    result_json = get_sanitized_inventory("all")
    result = json.loads(result_json)

    # Assert rtr1 is sanitized
    assert "rtr1" in result
    assert result["rtr1"]["host"] == "1.1.1.1"
    assert result["rtr1"]["device_type"] == "cisco_ios"
    assert result["rtr1"]["port"] == 22
    assert "username" not in result["rtr1"]
    assert "password" not in result["rtr1"]
    assert "secret" not in result["rtr1"]

    # Assert rtr2 is sanitized
    assert "rtr2" in result
    assert "password" not in result["rtr2"]


@patch("netmiko_mcp.inventory.obtain_devices")
def test_get_sanitized_inventory_handles_error(mock_obtain: Any) -> None:
    """Test that get_sanitized_inventory returns a structured JSON error if Netmiko fails."""
    mock_obtain.return_value = "Device or group not found"

    result_json = get_sanitized_inventory("bad_group")
    result = json.loads(result_json)

    assert "error" in result
    assert result["error"] == "Device or group not found"


@patch("netmiko_mcp.inventory.obtain_devices")
def test_get_device_names_success(mock_obtain: Any) -> None:
    """Test that get_device_names returns a list of device names."""
    mock_obtain.return_value = {
        "rtr1": {"host": "1.1.1.1"},
        "rtr2": {"host": "2.2.2.2"},
    }
    result = get_device_names("core")
    assert result == ["rtr1", "rtr2"]


@patch("netmiko_mcp.inventory.obtain_devices")
def test_get_device_names_error(mock_obtain: Any) -> None:
    """Test that get_device_names raises ValueError when group is not found."""
    mock_obtain.return_value = "Group not found"
    with pytest.raises(ValueError, match="Group not found"):
        get_device_names("nonexistent")


@patch("netmiko_mcp.inventory.settings")
def test_inventory_env_var_override(mock_settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that explicit inventory_file overrides NETMIKO_TOOLS_CFG."""
    from netmiko_mcp.inventory import _set_inventory_env_var

    mock_settings.inventory_type = "netmiko_tools"
    mock_settings.inventory_file = "/custom/mcp/inventory.yml"

    # Ensure it's cleared first
    monkeypatch.delenv("NETMIKO_TOOLS_CFG", raising=False)

    _set_inventory_env_var()
    assert os.environ.get("NETMIKO_TOOLS_CFG") == "/custom/mcp/inventory.yml"


@patch("netmiko_mcp.inventory.settings")
def test_inventory_env_var_fallback(mock_settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that if inventory_file is None, we DO NOT override NETMIKO_TOOLS_CFG."""
    from netmiko_mcp.inventory import _set_inventory_env_var

    mock_settings.inventory_type = "netmiko_tools"
    mock_settings.inventory_file = None

    # Set a pre-existing environment variable
    monkeypatch.setenv("NETMIKO_TOOLS_CFG", "/existing/native/netmiko.yml")

    _set_inventory_env_var()

    # Assert it was untouched
    assert os.environ.get("NETMIKO_TOOLS_CFG") == "/existing/native/netmiko.yml"

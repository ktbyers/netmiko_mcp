import json
from typing import Any
from unittest.mock import patch

from netmiko_mcp.server import get_device_params, list_devices, mcp, ping


def test_ping_tool() -> None:
    """Test that the ping tool returns the expected response."""
    assert ping() == "pong"


def test_mcp_initialization() -> None:
    """Test that the FastMCP server is initialized with the correct name."""
    assert mcp.name == "netmiko-mcp"


@patch("netmiko_mcp.server.obtain_devices")
def test_get_device_params_success(mock_obtain: Any) -> None:
    """Test that get_device_params returns the raw device dictionary."""
    mock_obtain.return_value = {"rtr1": {"host": "1.1.1.1", "username": "admin", "password": "pwd"}}
    result = get_device_params("rtr1")
    assert result["host"] == "1.1.1.1"
    assert result["password"] == "pwd"


@patch("netmiko_mcp.server.obtain_devices")
def test_get_device_params_not_found(mock_obtain: Any) -> None:
    """Test that get_device_params raises an error if the device isn't in the returned dict."""
    mock_obtain.return_value = {"rtr2": {"host": "2.2.2.2"}}
    import pytest

    with pytest.raises(ValueError, match="not found in inventory"):
        get_device_params("rtr1")


@patch("netmiko_mcp.server.obtain_devices")
def test_get_device_params_error_string(mock_obtain: Any) -> None:
    """Test that get_device_params raises an error if Netmiko returns an error string."""
    mock_obtain.return_value = "Error reading from netmiko devices file."
    import pytest

    with pytest.raises(ValueError, match="Error reading"):
        get_device_params("rtr1")


@patch("netmiko_mcp.server.obtain_devices")
def test_list_devices_sanitizes_credentials(mock_obtain: Any) -> None:
    """Test that list_devices strips username, password, and secret from the output."""
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

    result_json = list_devices("all")
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


@patch("netmiko_mcp.server.obtain_devices")
def test_list_devices_handles_error(mock_obtain: Any) -> None:
    """Test that list_devices returns a structured JSON error if Netmiko fails."""
    mock_obtain.return_value = "Device or group not found"

    result_json = list_devices("bad_group")
    result = json.loads(result_json)

    assert "error" in result
    assert result["error"] == "Device or group not found"

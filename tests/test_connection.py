from unittest.mock import MagicMock, patch

from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

from netmiko_mcp.connection import run_show_command


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
def test_run_show_command_success(
    mock_get_params: MagicMock, mock_connect: MagicMock, mock_validate: MagicMock
) -> None:
    """Test that a command is executed successfully and returns output."""
    mock_validate.return_value = True
    mock_get_params.return_value = {"host": "1.1.1.1", "device_type": "cisco_ios"}

    # Mock the context manager behavior of ConnectHandler
    mock_net_connect = MagicMock()
    mock_net_connect.send_command.return_value = "GigabitEthernet0/0 up up"
    mock_connect.return_value.__enter__.return_value = mock_net_connect

    result = run_show_command("rtr1", "show ip int brief")

    assert result == "GigabitEthernet0/0 up up"
    mock_connect.assert_called_once_with(host="1.1.1.1", device_type="cisco_ios")
    mock_net_connect.send_command.assert_called_once_with("show ip int brief", use_textfsm=False)


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
def test_run_show_command_textfsm(
    mock_get_params: MagicMock, mock_connect: MagicMock, mock_validate: MagicMock
) -> None:
    """Test that textfsm parsed data is correctly serialized to JSON."""
    mock_validate.return_value = True
    mock_get_params.return_value = {"host": "1.1.1.1"}

    mock_net_connect = MagicMock()
    # Simulate textfsm returning a list of dicts
    mock_net_connect.send_command.return_value = [{"intf": "Gi0/0", "status": "up"}]
    mock_connect.return_value.__enter__.return_value = mock_net_connect

    result = run_show_command("rtr1", "show ip int brief", use_textfsm=True)

    # It should return the list of dicts directly, not a JSON string
    assert isinstance(result, list)
    assert result[0]["intf"] == "Gi0/0"
    mock_net_connect.send_command.assert_called_once_with("show ip int brief", use_textfsm=True)


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.get_device_params")
def test_run_show_command_inventory_error(
    mock_get_params: MagicMock, mock_validate: MagicMock
) -> None:
    """Test that an inventory failure is caught and returned as a string."""
    mock_validate.return_value = True
    mock_get_params.side_effect = ValueError("Device not found")

    result = run_show_command("bad_router", "show version")
    assert result == "Inventory Error: Device not found"


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
def test_run_show_command_auth_error(
    mock_get_params: MagicMock, mock_connect: MagicMock, mock_validate: MagicMock
) -> None:
    """Test that an authentication failure is caught and returned as a string."""
    mock_validate.return_value = True
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.side_effect = NetmikoAuthenticationException("Auth failed")

    result = run_show_command("rtr1", "show version")
    assert result == "Connection Error: Authentication failed for device 'rtr1'."


@patch("netmiko_mcp.connection.validate_command")
@patch("netmiko_mcp.connection.ConnectHandler")
@patch("netmiko_mcp.connection.get_device_params")
def test_run_show_command_timeout_error(
    mock_get_params: MagicMock, mock_connect: MagicMock, mock_validate: MagicMock
) -> None:
    """Test that a timeout failure is caught and returned as a string."""
    mock_validate.return_value = True
    mock_get_params.return_value = {"host": "1.1.1.1"}
    mock_connect.side_effect = NetmikoTimeoutException("Timeout")

    result = run_show_command("rtr1", "show version")
    assert result == "Connection Error: Connection to device 'rtr1' timed out."

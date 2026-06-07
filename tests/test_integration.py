import json
import os
import time
from pathlib import Path

import pytest
from mcp.client.session import ClientSession


@pytest.mark.anyio
async def test_ping_integration(mcp_client: ClientSession) -> None:
    """Integration test using the official MCP client over stdio pipes."""
    result = await mcp_client.call_tool("ping", arguments={})

    assert len(result.content) == 1
    assert result.content[0].type == "text"
    assert getattr(result.content[0], "text", "") == "pong"


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_live_device_connection(mcp_client: ClientSession) -> None:
    """
    End-to-end integration test against a real network device.
    This simulates an MCP client asking for the inventory, and then executing a command.
    """
    # Test the inventory list
    inv_result = await mcp_client.call_tool("list_devices", arguments={"device_or_group": "cisco1"})

    assert len(inv_result.content) == 1
    assert inv_result.content[0].type == "text"
    inventory = json.loads(getattr(inv_result.content[0], "text", ""))

    # Assert cisco1 was found and credentials were sanitized
    assert "cisco1" in inventory
    assert inventory["cisco1"]["device_type"] == "cisco_ios"
    assert "password" not in inventory["cisco1"]

    # Test actual execution via the MCP tool
    cmd_result = await mcp_client.call_tool(
        "send_show_command",
        arguments={"device_name": "cisco1", "command": "show version", "use_textfsm": False},
    )

    assert len(cmd_result.content) == 1
    assert cmd_result.content[0].type == "text"
    output = getattr(cmd_result.content[0], "text", "")

    # Assert the router actually responded with standard IOS output
    assert (
        "Cisco IOS Software" in output or "Cisco Internetwork Operating System Software" in output
    )

    # Test piped execution via the MCP tool
    piped_result = await mcp_client.call_tool(
        "send_show_command",
        arguments={
            "device_name": "cisco1",
            "command": "show version | include Version",
            "use_textfsm": False,
        },
    )

    assert len(piped_result.content) == 1
    assert piped_result.content[0].type == "text"
    piped_output = getattr(piped_result.content[0], "text", "")

    # Assert the output was correctly filtered by the router
    assert "Version 15.5(3)M8" in piped_output
    assert "uptime is" not in piped_output  # Proves the output was filtered

    # 4. Test execution of a benign but explicitly denied piped command
    cmd_result_denied = await mcp_client.call_tool(
        "send_show_command",
        arguments={"device_name": "cisco1", "command": "show version | awk", "use_textfsm": False},
    )

    assert len(cmd_result_denied.content) == 1
    assert cmd_result_denied.content[0].type == "text"
    denied_output = getattr(cmd_result_denied.content[0], "text", "")
    assert "Security Error: Command 'show version | awk' is not permitted" in denied_output

    # 5. Test command injection block against a wildcard pattern in the integration test
    cmd_result_inject = await mcp_client.call_tool(
        "send_show_command",
        arguments={
            "device_name": "cisco1",
            "command": "show version ; reload",
            "use_textfsm": False,
        },
    )

    assert len(cmd_result_inject.content) == 1
    assert cmd_result_inject.content[0].type == "text"
    inject_output = getattr(cmd_result_inject.content[0], "text", "")
    assert "Security Error: Command 'show version ; reload' is not permitted" in inject_output


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_group_command_raw_output(mcp_client: ClientSession) -> None:
    """Group command returns a dict keyed by device name with raw output."""
    result = await mcp_client.call_tool(
        "send_show_command_to_group",
        arguments={"device_or_group": "all", "command": "show version", "save_output": False},
    )

    assert len(result.content) == 1
    assert result.content[0].type == "text"
    output = json.loads(getattr(result.content[0], "text", ""))

    # Both devices should be in the result
    assert "cisco1" in output
    assert "cisco2" in output

    # Each should contain real IOS output
    for device, text in output.items():
        assert isinstance(text, str), f"{device} output should be a string"
        assert (
            "Cisco IOS Software" in text or "Cisco Internetwork Operating System Software" in text
        ), f"{device} output does not look like IOS: {text[:100]}"


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_group_command_save_output_false(mcp_client: ClientSession) -> None:
    """save_output=False returns raw output, not file paths."""
    result = await mcp_client.call_tool(
        "send_show_command_to_group",
        arguments={"device_or_group": "all", "command": "show version", "save_output": False},
    )
    output = json.loads(getattr(result.content[0], "text", ""))
    for device, text in output.items():
        assert not str(text).startswith("Saved to:"), (
            f"{device}: expected raw output but got file path"
        )


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_group_command_save_output_true(mcp_client: ClientSession) -> None:
    """save_output=True writes per-device files and returns their paths."""
    result = await mcp_client.call_tool(
        "send_show_command_to_group",
        arguments={"device_or_group": "all", "command": "show version", "save_output": True},
    )
    output = json.loads(getattr(result.content[0], "text", ""))

    for device, value in output.items():
        assert str(value).startswith("Saved to:"), f"{device}: expected file path but got: {value}"
        file_path = Path(str(value).replace("Saved to: ", ""))
        assert file_path.exists(), f"Expected file not found: {file_path}"
        content = file_path.read_text(encoding="utf-8")
        assert (
            "Cisco IOS Software" in content
            or "Cisco Internetwork Operating System Software" in content
        ), f"{device}: saved file does not contain IOS output"
        # Verify file is under the default save_output_dir (~/.netmiko_mcp_tmp)
        expected_base = str(Path("~/.netmiko_mcp_tmp").expanduser())
        assert str(file_path).startswith(expected_base), (
            f"{device}: file not in expected save_output_dir ({expected_base})"
        )
        # Verify device name is used as subdirectory
        assert file_path.parent.name == device, (
            f"Expected subdirectory '{device}', got '{file_path.parent.name}'"
        )


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_group_command_threading(mcp_client: ClientSession) -> None:
    """Concurrent execution of two devices should be faster than sequential."""
    # Time a single device for baseline
    start = time.monotonic()
    await mcp_client.call_tool(
        "send_show_command",
        arguments={"device_name": "cisco1", "command": "show version"},
    )
    single_elapsed = time.monotonic() - start

    # Time both devices concurrently
    start = time.monotonic()
    result = await mcp_client.call_tool(
        "send_show_command_to_group",
        arguments={"device_or_group": "all", "command": "show version", "save_output": False},
    )
    group_elapsed = time.monotonic() - start

    output = json.loads(getattr(result.content[0], "text", ""))
    assert "cisco1" in output and "cisco2" in output

    # Both devices concurrently should take less than 1.5x the single device time.
    # This proves parallelism — sequential would take ~2x the single device time.
    assert group_elapsed < single_elapsed * 1.5, (
        f"Group ({group_elapsed:.2f}s) not faster than 1.5x single ({single_elapsed:.2f}s) — "
        f"threading may not be working"
    )


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_group_command_security_block(mcp_client: ClientSession) -> None:
    """A blocked command hard-stops without connecting to any device.
    Uses 'show running-config' which is not in the allowed_commands list —
    harmless if it somehow slipped through, unlike destructive commands.
    """
    result = await mcp_client.call_tool(
        "send_show_command_to_group",
        arguments={
            "device_or_group": "all",
            "command": "show running-config",
            "save_output": False,
        },
    )
    output = json.loads(getattr(result.content[0], "text", ""))
    assert "error" in output
    assert "Security Error" in output["error"]

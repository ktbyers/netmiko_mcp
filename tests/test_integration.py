import json
import os
import time
from pathlib import Path
from typing import Any

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
    reason="Requires real inventory file (.netmiko.yml) which is not committed. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_list_groups_integration(
    mcp_client: ClientSession, test_config: dict[str, Any]
) -> None:
    """list_groups returns the groups defined in the test inventory fixture."""
    result = await mcp_client.call_tool("list_groups", arguments={})

    assert len(result.content) == 1
    assert result.content[0].type == "text"
    groups = json.loads(getattr(result.content[0], "text", ""))

    assert isinstance(groups, list)
    assert test_config["test_group"] in groups
    assert "__meta__" not in groups
    for device in test_config["all_group_expected_devices"]:
        assert device not in groups


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_live_device_connection(
    mcp_client: ClientSession, test_config: dict[str, Any]
) -> None:
    """End-to-end integration test against a real network device."""
    device = test_config["test_device"]

    # Test the inventory list
    inv_result = await mcp_client.call_tool("list_devices", arguments={"device_or_group": device})

    assert len(inv_result.content) == 1
    assert inv_result.content[0].type == "text"
    inventory = json.loads(getattr(inv_result.content[0], "text", ""))

    assert device in inventory
    assert inventory[device]["device_type"] == test_config["test_device_type"]
    assert "password" not in inventory[device]

    # Test actual execution via the MCP tool
    cmd_result = await mcp_client.call_tool(
        "send_show_command",
        arguments={"device_name": device, "command": "show version", "use_textfsm": False},
    )

    assert len(cmd_result.content) == 1
    assert cmd_result.content[0].type == "text"
    output = getattr(cmd_result.content[0], "text", "")
    assert test_config["show_version_contains"] in output

    # Test piped execution via the MCP tool
    piped_result = await mcp_client.call_tool(
        "send_show_command",
        arguments={
            "device_name": device,
            "command": "show version | include Version",
            "use_textfsm": False,
        },
    )

    assert len(piped_result.content) == 1
    assert piped_result.content[0].type == "text"
    piped_output = getattr(piped_result.content[0], "text", "")
    assert test_config["show_version_pipe_contains"] in piped_output
    assert test_config["show_version_pipe_excludes"] not in piped_output

    # Test execution of a benign but explicitly denied piped command
    cmd_result_denied = await mcp_client.call_tool(
        "send_show_command",
        arguments={"device_name": device, "command": "show version | awk", "use_textfsm": False},
    )

    assert len(cmd_result_denied.content) == 1
    assert cmd_result_denied.content[0].type == "text"
    denied_output = getattr(cmd_result_denied.content[0], "text", "")
    assert "Security Error: Command 'show version | awk' is not permitted" in denied_output

    # Test command injection block
    cmd_result_inject = await mcp_client.call_tool(
        "send_show_command",
        arguments={
            "device_name": device,
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
async def test_group_command_raw_output(
    mcp_client: ClientSession, test_config: dict[str, Any]
) -> None:
    """Group command returns a dict keyed by device name with raw output."""
    result = await mcp_client.call_tool(
        "send_show_command_to_group",
        arguments={"device_or_group": "all", "command": "show version", "save_output": False},
    )

    assert len(result.content) == 1
    assert result.content[0].type == "text"
    output = json.loads(getattr(result.content[0], "text", ""))

    for device in test_config["all_group_expected_devices"]:
        assert device in output

    for device, text in output.items():
        assert isinstance(text, str), f"{device} output should be a string"
        assert test_config["show_version_contains"] in text, (
            f"{device} output does not look like expected: {text[:100]}"
        )


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_group_command_save_output_false(
    mcp_client: ClientSession, test_config: dict[str, Any]
) -> None:
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
async def test_group_command_save_output_true(
    mcp_client: ClientSession, test_config: dict[str, Any]
) -> None:
    """save_output=True writes per-device files and returns their paths."""
    result = await mcp_client.call_tool(
        "send_show_command_to_group",
        arguments={"device_or_group": "all", "command": "show version", "save_output": True},
    )
    output = json.loads(getattr(result.content[0], "text", ""))

    for device, value in output.items():
        assert str(value).startswith("Output saved as '"), (
            f"{device}: expected save notification but got: {value}"
        )
        filename = str(value).split("'")[1]
        expected_base = Path("~/.netmiko_mcp_tmp").expanduser()
        file_path = expected_base / device / filename
        assert file_path.exists(), f"Expected file not found: {file_path}"
        content = file_path.read_text(encoding="utf-8")
        assert test_config["show_version_contains"] in content, (
            f"{device}: saved file does not contain expected output"
        )


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_group_command_threading(
    mcp_client: ClientSession,
    mcp_client_sequential: ClientSession,
    test_config: dict[str, Any],
) -> None:
    """Parallel execution (max_workers=10) should be significantly faster than sequential
    (max_workers=1) across the test group.
    """
    group = test_config["test_group"]

    # Sequential run (max_workers=1) — devices connect one at a time
    start = time.monotonic()
    await mcp_client_sequential.call_tool(
        "send_show_command_to_group",
        arguments={"device_or_group": group, "command": "show version", "save_output": False},
    )
    sequential_elapsed = time.monotonic() - start

    # Parallel run (max_workers=10) — all devices connect concurrently
    start = time.monotonic()
    result = await mcp_client.call_tool(
        "send_show_command_to_group",
        arguments={"device_or_group": group, "command": "show version", "save_output": False},
    )
    parallel_elapsed = time.monotonic() - start

    output = json.loads(getattr(result.content[0], "text", ""))
    assert len(output) >= test_config["test_group_min_devices"], (
        f"Expected at least {test_config['test_group_min_devices']} devices in {group} group"
    )

    assert parallel_elapsed < sequential_elapsed / 1.5, (
        f"Parallel ({parallel_elapsed:.2f}s) not 1.5x faster than sequential "
        f"({sequential_elapsed:.2f}s) — threading may not be working correctly"
    )


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_group_command_textfsm(
    mcp_client: ClientSession, test_config: dict[str, Any]
) -> None:
    """use_textfsm=True returns structured JSON for each device in the group."""
    group = test_config["test_group"]
    result = await mcp_client.call_tool(
        "send_show_command_to_group",
        arguments={
            "device_or_group": group,
            "command": "show version",
            "use_textfsm": True,
            "save_output": False,
        },
    )

    assert len(result.content) == 1
    output = json.loads(getattr(result.content[0], "text", ""))

    assert len(output) >= test_config["test_group_min_devices"], (
        f"Expected at least {test_config['test_group_min_devices']} devices in {group} group"
    )
    for device, data in output.items():
        assert isinstance(data, list), (
            f"{device}: expected parsed list from textfsm but got {type(data).__name__}"
        )
        assert len(data) > 0, f"{device}: textfsm returned empty list"
        assert isinstance(data[0], dict), (
            f"{device}: expected list of dicts from textfsm but got list of {type(data[0]).__name__}"
        )


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_list_and_read_device_output_roundtrip(
    mcp_client: ClientSession, test_config: dict[str, Any]
) -> None:
    """Full round-trip: save output, list it, read it back and verify content."""
    group = test_config["test_group"]

    # Step 1 — save output for the test group
    save_result = await mcp_client.call_tool(
        "send_show_command_to_group",
        arguments={"device_or_group": group, "command": "show version", "save_output": True},
    )
    saved = json.loads(getattr(save_result.content[0], "text", ""))
    assert all(str(v).startswith("Output saved as '") for v in saved.values()), (
        f"Expected all values to be save notifications: {saved}"
    )

    # Step 2 — list saved files for the group
    list_result = await mcp_client.call_tool(
        "list_device_outputs",
        arguments={"device_or_group": group},
    )
    listing = json.loads(getattr(list_result.content[0], "text", ""))
    for device in saved:
        assert device in listing, f"{device} missing from listing"
        assert len(listing[device]) >= 1, f"{device} has no listed files"

    # Step 3 — read back the most recent file for each device
    for device, files in listing.items():
        filename = files[0]  # newest first
        read_result = await mcp_client.call_tool(
            "read_device_output",
            arguments={"device_name": device, "filename": filename},
        )
        content = getattr(read_result.content[0], "text", "")
        assert test_config["show_version_contains"] in content, (
            f"{device}: read content does not contain expected output"
        )


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_single_device_explicit_save(
    mcp_client: ClientSession, test_config: dict[str, Any]
) -> None:
    """send_show_command with save_output=True saves to disk and returns a filename notification."""
    device = test_config["test_device"]
    result = await mcp_client.call_tool(
        "send_show_command",
        arguments={"device_name": device, "command": "show version", "save_output": True},
    )
    text = getattr(result.content[0], "text", "")

    assert text.startswith("Output saved as '"), f"Unexpected response: {text!r}"
    filename = text.split("'")[1]

    list_result = await mcp_client.call_tool(
        "list_device_outputs", arguments={"device_or_group": device}
    )
    listing = json.loads(getattr(list_result.content[0], "text", ""))
    assert filename in listing.get(device, []), (
        f"Saved file '{filename}' not found in listing: {listing}"
    )

    read_result = await mcp_client.call_tool(
        "read_device_output",
        arguments={"device_name": device, "filename": filename},
    )
    content = getattr(read_result.content[0], "text", "")
    assert test_config["show_version_contains"] in content


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_single_device_auto_save(
    mcp_client_low_threshold: ClientSession, test_config: dict[str, Any]
) -> None:
    """send_show_command auto-saves when output exceeds save_threshold.
    Uses a 5-line threshold so any real show command triggers it.
    """
    device = test_config["test_device"]
    result = await mcp_client_low_threshold.call_tool(
        "send_show_command",
        arguments={"device_name": device, "command": "show version", "save_output": False},
    )
    text = getattr(result.content[0], "text", "")

    assert "Automatically saved as '" in text, f"Expected auto-save notification, got: {text!r}"
    filename = text.split("Automatically saved as '")[1].split("'")[0]

    list_result = await mcp_client_low_threshold.call_tool(
        "list_device_outputs", arguments={"device_or_group": device}
    )
    listing = json.loads(getattr(list_result.content[0], "text", ""))
    assert filename in listing.get(device, []), (
        f"Auto-saved file '{filename}' not found in listing: {listing}"
    )

    read_result = await mcp_client_low_threshold.call_tool(
        "read_device_output",
        arguments={"device_name": device, "filename": filename},
    )
    content = getattr(read_result.content[0], "text", "")
    assert test_config["show_version_contains"] in content


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_group_command_auto_save(
    mcp_client_low_threshold: ClientSession, test_config: dict[str, Any]
) -> None:
    """send_show_command_to_group with save_output=False auto-saves per-device output
    when it exceeds save_threshold. Uses a 5-line threshold.
    """
    group = test_config["test_group"]
    result = await mcp_client_low_threshold.call_tool(
        "send_show_command_to_group",
        arguments={"device_or_group": group, "command": "show version", "save_output": False},
    )
    output = json.loads(getattr(result.content[0], "text", ""))

    assert len(output) >= test_config["test_group_min_devices"], (
        f"Expected at least {test_config['test_group_min_devices']} devices, got: {list(output.keys())}"
    )
    for device, text in output.items():
        assert "Automatically saved as '" in str(text), (
            f"{device}: expected auto-save notification, got: {text!r}"
        )
        filename = str(text).split("Automatically saved as '")[1].split("'")[0]
        list_result = await mcp_client_low_threshold.call_tool(
            "list_device_outputs", arguments={"device_or_group": device}
        )
        listing = json.loads(getattr(list_result.content[0], "text", ""))
        assert filename in listing.get(device, []), (
            f"{device}: auto-saved file '{filename}' not in listing: {listing}"
        )


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_read_device_output_pagination(
    mcp_client: ClientSession, test_config: dict[str, Any]
) -> None:
    """Pagination round-trip: save show interfaces output, then read it back in 20-line pages.

    Verifies that:
    - The first page header correctly shows 'Lines 1-20 of N'
    - A continuation hint is present when more lines remain
    - The second page header correctly shows 'Lines 21-40 of N'
    - Content from each page is distinct (no overlap)
    """
    device = test_config["test_device"]

    # Step 1 — save 'show interfaces' output explicitly so we have a known file to paginate.
    # show interfaces typically produces well over 40 lines on any real IOS device.
    save_result = await mcp_client.call_tool(
        "send_show_command_to_group",
        arguments={"device_or_group": device, "command": "show interfaces", "save_output": True},
    )
    saved = json.loads(getattr(save_result.content[0], "text", ""))
    assert device in saved, f"Expected {device} in save result: {saved}"

    # Step 2 — list saved files to get the filename.
    list_result = await mcp_client.call_tool(
        "list_device_outputs",
        arguments={"device_or_group": device},
    )
    listing = json.loads(getattr(list_result.content[0], "text", ""))
    assert device in listing and len(listing[device]) >= 1, (
        f"No saved files found for {device}: {listing}"
    )
    filename = listing[device][0]  # newest file first

    # Step 3 — read page 1 (lines 1-20).
    page1_result = await mcp_client.call_tool(
        "read_device_output",
        arguments={"device_name": device, "filename": filename, "offset": 0, "limit": 20},
    )
    page1 = getattr(page1_result.content[0], "text", "")
    page1_lines = page1.splitlines()

    # Header is always the first line.
    assert page1_lines[0].startswith("Lines 1-20 of "), (
        f"Unexpected page 1 header: {page1_lines[0]!r}"
    )
    total_lines = int(page1_lines[0].split(" of ")[1].split(".")[0])
    assert total_lines > 20, (
        f"Expected more than 20 total lines for show interfaces, got {total_lines}"
    )
    assert "offset=20" in page1_lines[0], (
        f"Expected continuation hint with offset=20 in header: {page1_lines[0]!r}"
    )
    # 20 content lines follow the header.
    assert len(page1_lines) == 21, f"Expected 1 header + 20 content lines, got {len(page1_lines)}"

    # Step 4 — read page 2 (lines 21 to min(40, total)).
    page2_result = await mcp_client.call_tool(
        "read_device_output",
        arguments={"device_name": device, "filename": filename, "offset": 20, "limit": 20},
    )
    page2 = getattr(page2_result.content[0], "text", "")
    page2_lines = page2.splitlines()

    # End line depends on how many lines the device actually produced.
    expected_end = min(40, total_lines)
    assert page2_lines[0].startswith(f"Lines 21-{expected_end} of {total_lines}."), (
        f"Unexpected page 2 header: {page2_lines[0]!r}"
    )
    # Pages must cover different positions. Compare as ordered lists, not sets,
    # to avoid false failures from repeated blank lines or identical indentation.
    assert page1_lines[1:] != page2_lines[1:], (
        "Pages 1 and 2 returned identical content — pagination is not advancing"
    )


@pytest.mark.anyio
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_TESTS"),
    reason="Requires external network access and real credentials. Set RUN_LIVE_TESTS=1 to run.",
)
async def test_group_command_security_block(
    mcp_client: ClientSession, test_config: dict[str, Any]
) -> None:
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

import io
import json
import traceback
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from netmiko import ConnectHandler
from netmiko.base_connection import BaseConnection
from netmiko.exceptions import (
    NetmikoAuthenticationException,
    NetmikoBaseException,
    NetmikoTimeoutException,
    ReadException,
    ReadTimeout,
    WriteException,
)
from paramiko.ssh_exception import SSHException

from netmiko_mcp.audit import (
    ALLOWED,
    DENIED,
    OUTCOME_AUTH_FAILURE,
    OUTCOME_ERROR,
    OUTCOME_INVENTORY_ERROR,
    OUTCOME_NETMIKO_ERROR,
    OUTCOME_READ_ERROR,
    OUTCOME_READ_TIMEOUT,
    OUTCOME_SSH_ERROR,
    OUTCOME_SUCCESS,
    OUTCOME_TIMEOUT,
    OUTCOME_WRITE_ERROR,
    CommandAuditContext,
    save_channel_transcript,
)
from netmiko_mcp.config import settings
from netmiko_mcp.inventory import get_all_device_params, get_device_names, get_device_params
from netmiko_mcp.security import ValidationResult, validate_command


@contextmanager
def _managed_connection(
    connect_params: dict[str, Any],
) -> Generator[BaseConnection, None, None]:
    """Manage the SSH connection lifecycle for a single command execution.

    Establishes the Netmiko SSH connection and yields it to the caller.
    All connection-phase exceptions propagate to the caller without being
    caught here — run_show_command handles them in its outer except clauses
    where the correlation ID and audit context are available.

    On clean exit the session is disconnected. On any exception from the
    caller's block the connection is also disconnected and the exception
    re-raised. Discarding rather than recycling on error is intentional:
    channel state after a failed command is undefined, and a future connection
    pool should never receive a connection whose prompt may be dirty.

    When connection pooling is implemented this function is the right place
    to swap close-on-exit for return-to-pool-on-exit, without touching
    run_show_command.
    """
    net_connect = ConnectHandler(**connect_params)
    try:
        yield net_connect
    except Exception:
        net_connect.disconnect()
        raise
    else:
        net_connect.disconnect()


def run_show_command(
    device_name: str,
    command: str,
    use_textfsm: bool = False,
    save_output: bool = False,
    *,
    _tool_name: str = "send_show_command",
    _correlation_id: str | None = None,
    _preloaded_params: dict[str, Any] | None = None,
    _auto_save: bool = True,
) -> str | list[Any] | dict[str, Any]:
    """
    Connect to a network device and execute a single show command.

    Args:
        device_name: The name of the device in the inventory.
        command: The CLI command to execute.
        use_textfsm: If True, attempt to return parsed JSON data instead of raw text.

    Returns:
        The text output of the command (or structured data if parsed), or an error
        message string if validation, inventory lookup, or the connection fails.

    The _tool_name and _correlation_id keyword-only parameters are internal.
    _tool_name is recorded in audit log entries so group commands are attributed
    to send_show_command_to_group rather than this function's default. A new
    UUID correlation_id is generated per call if one is not provided, linking
    the command_attempt and connection_outcome audit records for the same
    operation.
    """
    correlation_id = _correlation_id or str(uuid.uuid4())
    audit_context = CommandAuditContext(
        correlation_id=correlation_id,
        tool=_tool_name,
        device=device_name,
        command=command,
    )

    # Validate the command and emit the audit record for the decision.
    result: ValidationResult = validate_command(command)
    audit_context.log_attempt(ALLOWED if result.allowed else DENIED, result.reason)
    if not result.allowed:
        return f"Security Error: Command '{command}' is not permitted."

    # Fetch device parameters. When called from run_show_command_on_group,
    # pre-loaded params are passed directly to avoid repeated inventory
    # decryption across concurrent threads.
    try:
        params = (
            _preloaded_params if _preloaded_params is not None else get_device_params(device_name)
        )
    except ValueError as e:
        audit_context.log_outcome(OUTCOME_INVENTORY_ERROR, detail=str(e))
        return f"Inventory Error: {str(e)}"

    # Optionally set up a BytesIO buffer as the session_log to capture the
    # channel read transcript. Network devices echo sent commands in the read
    # stream, so the transcript naturally records what was sent without
    # needing session_log_record_writes=True. Netmiko's SessionLog no_log
    # mechanism automatically filters password and secret from the buffer.
    session_log_buf: io.BytesIO | None = None
    connect_params: dict[str, Any] = dict(params)
    if settings.audit_log_read_transcript:
        session_log_buf = io.BytesIO()
        connect_params["session_log"] = session_log_buf

    # Connection phase (Block 1): _managed_connection establishes the SSH
    # session. Any exception raised by ConnectHandler before the yield
    # propagates out of the with statement and is caught by the outer except
    # clauses below. These are connection-level failures — auth rejection,
    # TCP timeout, SSH key exchange error, etc.
    try:
        with _managed_connection(connect_params) as net_connect:
            # Command phase (Block 2): the connection is established. Exceptions
            # here are distinct from connection failures — the SSH session is
            # healthy but something went wrong during command execution or output
            # reading. Each case is caught, logged, and returned individually so
            # the LLM receives a precise error rather than a generic message.
            try:
                output = net_connect.send_command(command, use_textfsm=use_textfsm)

                # use_textfsm falls back to raw text when no template exists. A string
                # return when use_textfsm=True was requested indicates the fallback.
                textfsm_parse_failed = use_textfsm and isinstance(output, str)

                # If use_textfsm successfully parsed it, it returns a List or Dict.
                # Return this directly so the MCP framework can serialise it without
                # causing double JSON serialisation.
                final_output: str | list[Any] | dict[str, Any]
                if isinstance(output, (list, dict)):
                    final_output = output
                else:
                    final_output = str(output)

            except ReadTimeout:
                audit_context.log_outcome(OUTCOME_READ_TIMEOUT)
                return (
                    f"Connection Error: Device '{device_name}' stopped responding "
                    f"while reading command output."
                )
            except ReadException as e:
                audit_context.log_outcome(OUTCOME_READ_ERROR, detail=str(e))
                return f"Connection Error: Failed to read output from '{device_name}': {str(e)}"
            except WriteException as e:
                audit_context.log_outcome(OUTCOME_WRITE_ERROR, detail=str(e))
                return f"Connection Error: Failed to send command to '{device_name}': {str(e)}"
            except NetmikoBaseException as e:
                audit_context.log_outcome(OUTCOME_NETMIKO_ERROR, detail=str(e))
                return f"Connection Error: {str(e)}"
            except Exception as e:
                # Unexpected exception during command execution — almost certainly
                # a bug. The full traceback is written to the audit log detail
                # field so developers can locate the source without a separate
                # logging pipeline.
                audit_context.log_outcome(OUTCOME_ERROR, detail=traceback.format_exc())
                return f"Execution Error: An unexpected error occurred: {str(e)}"

            # Explicit save requested — persist output to disk regardless of size.
            # Takes priority over the threshold-based auto-save below.
            if save_output:
                saved_path_str = _save_device_output(device_name, command, final_output)
                saved_filename = Path(saved_path_str).name
                final_output = f"Output saved as '{saved_filename}'."
            # Automatically save output that exceeds the configured line threshold
            # rather than returning it inline. This prevents large outputs (e.g. a
            # full BGP table) from overwhelming the LLM's context window. The full
            # path is not included in the return message — the client should use
            # list_device_outputs and read_device_output to retrieve the content.
            elif _auto_save:
                as_str = (
                    json.dumps(final_output, indent=2)
                    if isinstance(final_output, (list, dict))
                    else str(final_output)
                )
                line_count = len(as_str.splitlines())
                if line_count > settings.save_threshold:
                    saved_path_str = _save_device_output(device_name, command, final_output)
                    saved_filename = Path(saved_path_str).name
                    final_output = (
                        f"Output too large to return inline ({line_count:,} lines, "
                        f"exceeds save_threshold of {settings.save_threshold:,}). "
                        f"Automatically saved as '{saved_filename}'. "
                        f"Use read_device_output to retrieve it."
                    )

            if session_log_buf is not None:
                save_channel_transcript(correlation_id, device_name, session_log_buf.getvalue())
            audit_context.log_outcome(OUTCOME_SUCCESS, textfsm_parse_failed=textfsm_parse_failed)
            return final_output

    except NetmikoAuthenticationException:
        audit_context.log_outcome(OUTCOME_AUTH_FAILURE)
        return f"Connection Error: Authentication failed for device '{device_name}'."
    except NetmikoTimeoutException:
        audit_context.log_outcome(OUTCOME_TIMEOUT)
        return f"Connection Error: Connection to device '{device_name}' timed out."
    except SSHException as e:
        audit_context.log_outcome(OUTCOME_SSH_ERROR, detail=str(e))
        return f"Connection Error: SSH protocol error for '{device_name}': {str(e)}"
    except NetmikoBaseException as e:
        audit_context.log_outcome(OUTCOME_NETMIKO_ERROR, detail=str(e))
        return f"Connection Error: {str(e)}"
    except Exception as e:
        # Unexpected exception during connection establishment — almost certainly
        # a bug or an unknown OS/network error. The full traceback is written to
        # the audit log detail field so developers can locate the source.
        audit_context.log_outcome(OUTCOME_ERROR, detail=traceback.format_exc())
        return f"Execution Error: An unexpected error occurred: {str(e)}"


# Sequences rejected as substrings within any path component.
# Extend this list to tighten validation over time.
_UNSAFE_PATH_CHARS: list[str] = [
    "/",  # Unix path separator
    "\\",  # Windows path separator
    "..",  # parent directory traversal
    "\x00",  # null byte
    "\u2215",  # DIVISION SLASH (Unicode slash lookalike)
    "\uff0f",  # FULLWIDTH SOLIDUS (Unicode slash lookalike)
    "\u2044",  # FRACTION SLASH (Unicode slash lookalike)
    "\u29f8",  # BIG SOLIDUS (Unicode slash lookalike)
    "\uff3c",  # FULLWIDTH REVERSE SOLIDUS (Unicode backslash lookalike)
    "\u29f5",  # REVERSE SOLIDUS OPERATOR (Unicode backslash lookalike)
    "\u2216",  # SET MINUS (Unicode backslash lookalike)
    "\u29f9",  # BIG REVERSE SOLIDUS (Unicode backslash lookalike)
]

# Exact values rejected as a complete path component. A single dot collapses
# device_dir to base_dir; an empty string does the same.
_UNSAFE_PATH_VALUES: frozenset[str] = frozenset({"", "."})


def _validate_path_component(value: str, label: str) -> None:
    """Raise ValueError if value is in _UNSAFE_PATH_VALUES or contains any
    sequence in _UNSAFE_PATH_CHARS.

    Centralises path-component validation so that the rule set can be
    extended in one place. The label parameter names the argument being
    checked (e.g. "device name" or "filename") so callers get a precise
    error message.
    """
    if value in _UNSAFE_PATH_VALUES:
        raise ValueError(f"Security Error: Unsafe path value (src: {label}, value: {value!r})")
    if any(unsafe in value for unsafe in _UNSAFE_PATH_CHARS):
        raise ValueError(
            f"Security Error: Insecure characters detected in path (src: {label}, value: {value})"
        )


def _sanitize_command_for_filename(command: str) -> str:
    """Convert a command string into a safe filename component.
    Normalizes whitespace and replaces non-alphanumeric characters with underscores.
    Truncated to 50 characters to keep filenames manageable.
    """
    normalized = "_".join(command.split())
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in normalized)
    return safe[:50]


def _save_device_output(device_name: str, command: str, output: Any) -> str:
    """Save command output to a per-device file and return the absolute file path.

    Directories are created with mode 0o700 (owner read/write/execute only) to
    prevent other users on the system from reading potentially sensitive network
    device output.
    """
    _validate_path_component(device_name, "device name")
    base_dir = Path(settings.save_output_dir).expanduser()
    base_dir.mkdir(parents=True, exist_ok=True)
    base_dir.chmod(0o700)

    device_dir = base_dir / device_name
    device_dir.mkdir(exist_ok=True)
    device_dir.chmod(0o700)

    cmd_name = _sanitize_command_for_filename(command)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    file_path = device_dir / f"{cmd_name}_{timestamp}.txt"
    content = json.dumps(output, indent=2) if isinstance(output, (list, dict)) else str(output)
    file_path.write_text(content, encoding="utf-8")
    file_path.chmod(0o600)
    return str(file_path)


def list_device_outputs(device_or_group: str) -> dict[str, Any]:
    """List saved output files for a device, group, or all devices.

    Args:
        device_or_group: A device name, group name, or 'all'.

    Returns:
        A dict mapping each device name to a list of saved filenames (newest first).
        Devices with no saved output are included with an empty list.
    """
    try:
        device_names = get_device_names(device_or_group)
    except ValueError as e:
        return {"error": f"Inventory Error: {str(e)}"}

    base_dir = Path(settings.save_output_dir).expanduser()
    result: dict[str, Any] = {}

    for device_name in device_names:
        device_dir = base_dir / device_name
        if not device_dir.is_dir():
            result[device_name] = []
        else:
            result[device_name] = sorted(
                [f.name for f in device_dir.glob("*.txt")],
                reverse=True,
            )

    return result


def read_device_output(
    device_name: str,
    filename: str,
    offset: int = 0,
    limit: int = 500,
) -> str:
    """Read a previously saved output file for a specific device, with pagination.

    Both device_name and filename are validated to prevent path traversal attacks.

    Args:
        device_name: The device name whose output directory to read from.
        filename: The exact filename as returned by list_device_outputs.
        offset: Line number to start reading from (0-indexed). Defaults to 0.
        limit: Maximum number of lines to return. Defaults to 500.

    Returns:
        A paginated slice of the file with a header showing line range and total,
        plus a continuation hint when more lines remain. Returns an error message
        string on validation failure or if the file is not found.
    """
    try:
        _validate_path_component(device_name, "device name")
        _validate_path_component(filename, "filename")
    except ValueError as e:
        return str(e)

    base_dir = Path(settings.save_output_dir).expanduser()
    device_dir = base_dir / device_name
    file_path = device_dir / filename

    # Resolve the final path and confirm it sits inside base_dir. This catches
    # bypasses that survive string validation, such as symlinks that point
    # outside the permitted directory. Anchoring to base_dir rather than
    # device_dir ensures the check is against the operator-controlled root.
    try:
        if not file_path.resolve().is_relative_to(base_dir.resolve()):
            return f"Security Error: Path resolves outside restricted directory (device: {device_name}, file: {filename})"
    except Exception:  # pragma: no cover
        return f"Security Error: Path resolves outside restricted directory (device: {device_name}, file: {filename})"

    if not device_dir.is_dir():
        return f"Error: No saved output found for device '{device_name}'."
    if not file_path.is_file():
        return f"Error: File '{filename}' not found for device '{device_name}'."

    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    total = len(lines)

    if total == 0:
        return "Lines 0-0 of 0.\n"

    if offset >= total:
        return (
            f"Error: offset {offset} is beyond end of file "
            f"({total} line{'s' if total != 1 else ''})."
        )

    end = min(offset + limit, total)
    page = lines[offset:end]

    display_start = offset + 1  # 1-indexed for readability
    if end < total:
        continuation = f" Call read_device_output with offset={end} to continue."
    else:
        continuation = ""

    header = f"Lines {display_start}-{end} of {total}.{continuation}"
    return header + "\n" + "\n".join(page)


def run_show_command_on_group(
    device_or_group: str,
    command: str,
    use_textfsm: bool = False,
    save_output: bool = False,
) -> dict[str, Any]:
    """
    Execute a show command on a group of devices concurrently using threading.

    The command is validated once before any connections are made. If the command
    is not permitted, an audit record is emitted for the group-level denial and a
    security error is returned immediately without connecting to any device.

    Per-device audit records (both command_attempt and connection_outcome) are
    emitted by run_show_command within each thread.

    Args:
        device_or_group: A device name or group name from the inventory.
        command: The CLI command to execute on all devices.
        use_textfsm: If True, attempt to return parsed structured JSON data.
        save_output: If True, save per-device output to files under save_output_dir
                     and return file paths instead of raw output.

    Returns:
        A dict mapping each device name to its output (or saved file path).
    """
    # Pre-validate the command before attempting any connections. If denied, emit
    # a group-level audit record so the denial is never invisible, then return.
    result: ValidationResult = validate_command(command)
    if not result.allowed:
        correlation_id = str(uuid.uuid4())
        audit_context = CommandAuditContext(
            correlation_id=correlation_id,
            tool="send_show_command_to_group",
            device=f"GROUP:{device_or_group}",
            command=command,
        )
        audit_context.log_attempt(DENIED, result.reason)
        return {"error": f"Security Error: Command '{command}' is not permitted."}

    # Load all device params once before spawning threads to avoid repeated
    # inventory decryption inside each thread, which serializes concurrent
    # connections and significantly increases wall-clock time for group commands.
    try:
        all_device_params = get_all_device_params(device_or_group)
    except ValueError as e:
        return {"error": f"Inventory Error: {str(e)}"}

    results: dict[str, Any] = {}

    with ThreadPoolExecutor(max_workers=settings.max_workers) as executor:
        future_to_device = {
            executor.submit(
                run_show_command,
                name,
                command,
                use_textfsm,
                False,  # save_output=False — group runner handles explicit saves
                _tool_name="send_show_command_to_group",
                _preloaded_params=params,
                _auto_save=not save_output,  # auto-save applies only when not explicitly saving
            ): name
            for name, params in all_device_params.items()
        }
        for future in as_completed(future_to_device):
            device_name = future_to_device[future]
            try:
                output = future.result()
                if save_output:
                    saved_path_str = _save_device_output(device_name, command, output)
                    saved_filename = Path(saved_path_str).name
                    results[device_name] = f"Output saved as '{saved_filename}'."
                else:
                    results[device_name] = output
            except Exception as e:
                results[device_name] = f"Execution Error: {str(e)}"

    return results

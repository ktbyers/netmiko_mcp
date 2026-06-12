"""
Audit logging for the Netmiko MCP server.

Every MCP tool invocation should produce an audit record. For device commands
this means two records: one at validation time (showing the verdict and reason)
and one after the connection attempt (showing the outcome). Non-device tools
(ping, list_devices, list_device_outputs, read_device_output) each produce a
single tool-invocation record.

All records are emitted as single-line JSON via a dedicated logger named
'netmiko_mcp.audit', which is isolated from the general application logger so
audit records cannot be accidentally suppressed or mixed with debug output.

When audit_log_enabled is True, any handler that fails to write raises a
RuntimeError so the calling operation also fails. No command should be executed
without a corresponding audit record (fail-closed policy).

Reason constants defined here are used by security.py to populate
ValidationResult.reason so that audit consumers have consistent, queryable
strings without hard-coding values in multiple places.
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from netmiko_mcp.config import settings

# ---------------------------------------------------------------------------
# Verdict constants — recorded in command_attempt audit records.
# ---------------------------------------------------------------------------

ALLOWED = "ALLOWED"
DENIED = "DENIED"

# ---------------------------------------------------------------------------
# Reason constants — used by security.validate_command to populate
# ValidationResult.reason and recorded verbatim in audit log entries.
# ---------------------------------------------------------------------------

REASON_UNSAFE_CHAR = "UNSAFE_CHAR"
REASON_DENY_MATCH = "DENY_MATCH"
REASON_PIPE_NOT_ALLOWED = "PIPE_NOT_ALLOWED"
REASON_MULTIPLE_PIPES = "MULTIPLE_PIPES"
REASON_INVALID_PIPE_MODIFIER = "INVALID_PIPE_MODIFIER"
REASON_NO_ALLOW_MATCH = "NO_ALLOW_MATCH"
REASON_ALLOWED = "ALLOWED"

# ---------------------------------------------------------------------------
# Connection outcome constants — recorded in connection_outcome audit records.
# ---------------------------------------------------------------------------

OUTCOME_SUCCESS = "SUCCESS"
OUTCOME_AUTH_FAILURE = "AUTH_FAILURE"
OUTCOME_TIMEOUT = "TIMEOUT"
OUTCOME_ERROR = "ERROR"
OUTCOME_INVENTORY_ERROR = "INVENTORY_ERROR"

# ---------------------------------------------------------------------------
# Dedicated audit logger.
# ---------------------------------------------------------------------------

_audit_logger = logging.getLogger("netmiko_mcp.audit")

# A NullHandler is added at import time following the standard library pattern
# for library loggers. This prevents spurious "No handlers could be found"
# warnings in environments where audit logging has not been configured (tests,
# embedded use). Real handlers are attached by configure_audit_logger().
_audit_logger.addHandler(logging.NullHandler())

# Standard LogRecord attributes that are excluded from JSON output so only our
# structured fields appear alongside timestamp and level in each record.
_LOGRECORD_BUILTIN_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


# ---------------------------------------------------------------------------
# JSON formatter and fail-closed handlers.
# ---------------------------------------------------------------------------


class _AuditJsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects.

    The timestamp is written in ISO 8601 UTC format. All extra fields attached
    to the LogRecord via the logging extra= parameter are included alongside the
    standard timestamp and level fields.
    """

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
        }
        for key, value in record.__dict__.items():
            if key not in _LOGRECORD_BUILTIN_ATTRS:
                data[key] = value
        return json.dumps(data, default=str)


class _FailClosedFileHandler(logging.FileHandler):
    """A FileHandler that re-raises write errors rather than swallowing them.

    Python's default handler behaviour catches exceptions in emit() and routes
    them to handleError(), which prints to stderr. For audit logging this is
    insufficient — a failed write should propagate so the caller fails closed.
    File rotation is left to the operator (e.g. logrotate).
    """

    def handleError(self, record: logging.LogRecord) -> None:
        _, exc_value, _ = sys.exc_info()
        raise RuntimeError(f"Audit log file write failed: {exc_value}") from exc_value


class _FailClosedSysLogHandler(logging.handlers.SysLogHandler):
    """A SysLogHandler that re-raises write errors rather than swallowing them."""

    def handleError(self, record: logging.LogRecord) -> None:
        _, exc_value, _ = sys.exc_info()
        raise RuntimeError(f"Audit syslog write failed: {exc_value}") from exc_value


def _build_file_handler(formatter: logging.Formatter) -> _FailClosedFileHandler:
    """Construct and return a fail-closed file handler for the audit log."""
    log_path = Path(settings.audit_log_file).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = _FailClosedFileHandler(filename=str(log_path), mode="a", encoding="utf-8")
    if log_path.exists():
        log_path.chmod(0o600)
    handler.setFormatter(formatter)
    return handler


def _build_syslog_handler(formatter: logging.Formatter) -> _FailClosedSysLogHandler:
    """Construct and return a fail-closed syslog handler for the audit log.

    The audit_log_syslog_address setting may be a UNIX socket path such as
    '/dev/log', or a 'host:port' string for remote UDP syslog. The facility
    is resolved by name from audit_log_syslog_facility and defaults to local0.
    """
    address_str = settings.audit_log_syslog_address
    address: str | tuple[str, int]
    if ":" in address_str and not address_str.startswith("/"):
        host, port_str = address_str.rsplit(":", 1)
        address = (host, int(port_str))
    else:
        address = address_str

    facility = logging.handlers.SysLogHandler.facility_names.get(
        settings.audit_log_syslog_facility,
        logging.handlers.SysLogHandler.LOG_LOCAL0,
    )
    handler = _FailClosedSysLogHandler(address=address, facility=facility)  # type: ignore[arg-type]
    handler.setFormatter(formatter)
    return handler


# ---------------------------------------------------------------------------
# Public configuration entry-point.
# ---------------------------------------------------------------------------


def configure_audit_logger() -> None:
    """Configure the audit logger based on current settings.

    This should be called once at server startup before any tool invocations.
    It attaches handlers for the configured destination (local rotating file,
    syslog, or both). When audit_log_enabled is False this is a no-op — the
    NullHandler added at import time ensures the logger stays silent without
    any spurious warnings.
    """
    if not settings.audit_log_enabled:
        return

    _audit_logger.setLevel(logging.INFO)
    _audit_logger.propagate = False

    formatter = _AuditJsonFormatter()
    destination = settings.audit_log_destination

    if destination in ("file", "both"):
        _audit_logger.addHandler(_build_file_handler(formatter))
    if destination in ("syslog", "both"):
        _audit_logger.addHandler(_build_syslog_handler(formatter))


# ---------------------------------------------------------------------------
# Internal emit helper.
# ---------------------------------------------------------------------------


def _emit(fields: dict[str, Any]) -> None:
    """Emit one structured audit record via the audit logger.

    All fields are passed as extra LogRecord attributes and serialised to JSON
    by _AuditJsonFormatter. When audit_log_enabled is False the call is a no-op.
    When a handler raises (because _FailClosedHandler.handleError re-raises the
    original exception), that exception propagates to the caller enforcing the
    fail-closed policy.
    """
    if not settings.audit_log_enabled:
        return
    _audit_logger.info("audit", extra=fields)


# ---------------------------------------------------------------------------
# Public audit functions.
# ---------------------------------------------------------------------------


def log_command_attempt(
    *,
    correlation_id: str,
    tool: str,
    device: str,
    command: str,
    verdict: str,
    reason: str,
) -> None:
    """Emit an audit record for a command validation attempt.

    Called immediately after validate_command() returns, whether the command
    was allowed or denied. The reason field should be one of the REASON_*
    constants defined in this module.
    """
    _emit(
        {
            "event": "command_attempt",
            "correlation_id": correlation_id,
            "tool": tool,
            "device": device,
            "command": command,
            "verdict": verdict,
            "reason": reason,
        }
    )


def log_connection_outcome(
    *,
    correlation_id: str,
    tool: str,
    device: str,
    command: str,
    outcome: str,
    detail: Optional[str] = None,
    textfsm_parse_failed: bool = False,
) -> None:
    """Emit an audit record for a connection and command execution outcome.

    Called after the SSH connection attempt completes — successfully or not.
    The outcome field should be one of the OUTCOME_* constants defined in this
    module. detail carries exception messages on failures. textfsm_parse_failed
    is set when use_textfsm=True was requested but parsing fell back to raw text.
    """
    fields: dict[str, Any] = {
        "event": "connection_outcome",
        "correlation_id": correlation_id,
        "tool": tool,
        "device": device,
        "command": command,
        "outcome": outcome,
    }
    if detail is not None:
        fields["detail"] = detail
    if textfsm_parse_failed:
        fields["textfsm_parse_failed"] = True
    _emit(fields)


def log_tool_invocation(*, tool: str, arguments: dict[str, Any]) -> None:
    """Emit an audit record for a non-device MCP tool invocation.

    Used for tools that do not execute commands on network devices: ping,
    list_devices, list_device_outputs, and read_device_output. These tools
    should still produce an audit trail so every MCP operation is accounted for.
    """
    _emit(
        {
            "event": "tool_invocation",
            "tool": tool,
            "arguments": arguments,
        }
    )


# ---------------------------------------------------------------------------
# Channel read transcript helpers.
# ---------------------------------------------------------------------------


def save_channel_transcript(
    correlation_id: str,
    device_name: str,
    raw_bytes: bytes,
) -> None:
    """Save the SSH channel read transcript to a per-connection file.

    Transcript files are named by timestamp, correlation ID, and device so they
    can be joined with audit event records during incident investigation. Old
    files beyond audit_log_retention_days are removed on each write.

    This function should only be called when audit_log_read_transcript is True.
    The caller is responsible for checking the setting before creating the
    BytesIO buffer that feeds raw_bytes.

    Because SSH terminal echo means the device reflects sent commands back
    through the read channel, the transcript naturally captures what was sent
    without needing to tap the write side directly.
    """
    transcript_dir = Path(settings.audit_log_transcript_dir).expanduser()
    transcript_dir.mkdir(parents=True, exist_ok=True)
    transcript_dir.chmod(0o700)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_device = "".join(c if c.isalnum() or c in "-_." else "_" for c in device_name)
    filename = f"{timestamp}_{correlation_id}_{safe_device}.txt"
    file_path = transcript_dir / filename

    # decode with errors="replace" so this never raises in practice.
    transcript_text = raw_bytes.decode("utf-8", errors="replace")

    file_path.write_text(transcript_text, encoding="utf-8")
    file_path.chmod(0o600)

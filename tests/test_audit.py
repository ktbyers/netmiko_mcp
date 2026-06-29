"""Tests for the audit logging module."""

import json
import logging
import logging.handlers
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from netmiko_mcp.audit import (
    ALLOWED,
    DENIED,
    OUTCOME_AUTH_FAILURE,
    OUTCOME_ERROR,
    OUTCOME_INVENTORY_ERROR,
    OUTCOME_SUCCESS,
    OUTCOME_TIMEOUT,
    REASON_ALLOWED,
    REASON_DENY_MATCH,
    REASON_INVALID_PIPE_MODIFIER,
    REASON_MULTIPLE_PIPES,
    REASON_NO_ALLOW_MATCH,
    REASON_UNSAFE_CHAR,
    _AuditJsonFormatter,
    _FailClosedFileHandler,
    _FailClosedSysLogHandler,
    _audit_logger,
    _build_file_handler,
    _emit,
    configure_audit_logger,
    log_command_attempt,
    log_connection_outcome,
    log_tool_invocation,
    save_channel_transcript,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_verdict_constants() -> None:
    assert ALLOWED == "ALLOWED"
    assert DENIED == "DENIED"


def test_reason_constants_are_distinct_strings() -> None:
    reasons = [
        REASON_UNSAFE_CHAR,
        REASON_DENY_MATCH,
        REASON_MULTIPLE_PIPES,
        REASON_INVALID_PIPE_MODIFIER,
        REASON_NO_ALLOW_MATCH,
        REASON_ALLOWED,
    ]
    assert len(reasons) == len(set(reasons)), "Reason constants should be unique strings"


def test_outcome_constants_are_distinct_strings() -> None:
    outcomes = [
        OUTCOME_SUCCESS,
        OUTCOME_AUTH_FAILURE,
        OUTCOME_TIMEOUT,
        OUTCOME_ERROR,
        OUTCOME_INVENTORY_ERROR,
    ]
    assert len(outcomes) == len(set(outcomes)), "Outcome constants should be unique strings"


# ---------------------------------------------------------------------------
# _AuditJsonFormatter
# ---------------------------------------------------------------------------


def _make_record(extra: dict[str, Any]) -> logging.LogRecord:
    """Create a LogRecord with extra fields attached, as logging.info() would."""
    record = logging.LogRecord(
        name="netmiko_mcp.audit",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="audit",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_produces_valid_json() -> None:
    formatter = _AuditJsonFormatter()
    record = _make_record({"event": "command_attempt", "verdict": ALLOWED})
    output = formatter.format(record)
    data = json.loads(output)
    assert isinstance(data, dict)


def test_json_formatter_includes_timestamp() -> None:
    formatter = _AuditJsonFormatter()
    record = _make_record({"event": "test"})
    data = json.loads(formatter.format(record))
    assert "timestamp" in data
    assert "T" in data["timestamp"]  # ISO 8601 UTC


def test_json_formatter_includes_level() -> None:
    formatter = _AuditJsonFormatter()
    record = _make_record({"event": "test"})
    data = json.loads(formatter.format(record))
    assert data["level"] == "INFO"


def test_json_formatter_includes_extra_fields() -> None:
    formatter = _AuditJsonFormatter()
    record = _make_record(
        {
            "event": "command_attempt",
            "correlation_id": "abc-123",
            "tool": "send_show_command",
            "device": "router1",
            "command": "show version",
            "verdict": ALLOWED,
            "reason": REASON_ALLOWED,
        }
    )
    data = json.loads(formatter.format(record))
    assert data["event"] == "command_attempt"
    assert data["correlation_id"] == "abc-123"
    assert data["tool"] == "send_show_command"
    assert data["device"] == "router1"
    assert data["command"] == "show version"
    assert data["verdict"] == ALLOWED
    assert data["reason"] == REASON_ALLOWED


def test_json_formatter_excludes_standard_logrecord_attrs() -> None:
    formatter = _AuditJsonFormatter()
    record = _make_record({"event": "test"})
    data = json.loads(formatter.format(record))
    for attr in ("msg", "args", "filename", "funcName", "lineno", "module"):
        assert attr not in data, f"Standard LogRecord attr '{attr}' should not appear in output"


# ---------------------------------------------------------------------------
# _FailClosedFileHandler
# ---------------------------------------------------------------------------


def test_fail_closed_file_handler_raises_on_error(tmp_path: Path) -> None:
    """handleError should re-raise rather than swallow the write failure."""
    handler = _FailClosedFileHandler(
        filename=str(tmp_path / "audit.log"),
        mode="a",
        encoding="utf-8",
    )
    record = _make_record({"event": "test"})
    with pytest.raises(RuntimeError, match="Audit log file write failed"):
        try:
            raise OSError("disk full")
        except OSError:
            handler.handleError(record)


# ---------------------------------------------------------------------------
# _FailClosedSysLogHandler
# ---------------------------------------------------------------------------


def test_fail_closed_syslog_handler_raises_on_error() -> None:
    """handleError should re-raise rather than swallow the write failure."""
    # Construct with a fake address — we never actually emit to it.
    handler = _FailClosedSysLogHandler.__new__(_FailClosedSysLogHandler)
    record = _make_record({"event": "test"})
    with pytest.raises(RuntimeError, match="Audit syslog write failed"):
        try:
            raise ConnectionRefusedError("syslog unreachable")
        except ConnectionRefusedError:
            handler.handleError(record)


# ---------------------------------------------------------------------------
# configure_audit_logger
# ---------------------------------------------------------------------------


def _fresh_audit_logger() -> logging.Logger:
    """Return the audit logger with all non-NullHandler handlers removed."""
    logger = logging.getLogger("netmiko_mcp.audit")
    logger.handlers = [h for h in logger.handlers if isinstance(h, logging.NullHandler)]
    return logger


@patch("netmiko_mcp.audit.settings")
def test_configure_audit_logger_disabled(mock_settings: MagicMock) -> None:
    """When audit_log_enabled is False, no real handlers should be added."""
    mock_settings.audit_log_enabled = False
    logger = _fresh_audit_logger()
    handler_count_before = len(logger.handlers)
    configure_audit_logger()
    real_handlers = [h for h in logger.handlers if not isinstance(h, logging.NullHandler)]
    assert len(real_handlers) == 0
    logger.handlers = logger.handlers[:handler_count_before]


@patch("netmiko_mcp.audit.settings")
def test_configure_audit_logger_file_destination(mock_settings: MagicMock, tmp_path: Path) -> None:
    """When destination is 'file', a FileHandler should be attached."""
    mock_settings.audit_log_enabled = True
    mock_settings.audit_log_destination = "file"
    mock_settings.audit_log_file = str(tmp_path / "audit.log")
    logger = _fresh_audit_logger()
    configure_audit_logger()
    file_handlers = [h for h in logger.handlers if isinstance(h, _FailClosedFileHandler)]
    assert len(file_handlers) >= 1
    logger.handlers = [h for h in logger.handlers if isinstance(h, logging.NullHandler)]


@patch("netmiko_mcp.audit.settings")
def test_configure_audit_logger_syslog_destination(mock_settings: MagicMock) -> None:
    """When destination is 'syslog', a SysLogHandler should be attached."""
    mock_settings.audit_log_enabled = True
    mock_settings.audit_log_destination = "syslog"
    mock_settings.audit_log_syslog_address = "127.0.0.1:514"
    mock_settings.audit_log_syslog_facility = "local0"
    logger = _fresh_audit_logger()
    configure_audit_logger()
    syslog_handlers = [h for h in logger.handlers if isinstance(h, _FailClosedSysLogHandler)]
    assert len(syslog_handlers) >= 1
    logger.handlers = [h for h in logger.handlers if isinstance(h, logging.NullHandler)]


@patch("netmiko_mcp.audit.settings")
def test_configure_audit_logger_both_destinations(mock_settings: MagicMock, tmp_path: Path) -> None:
    """When destination is 'both', both a file and syslog handler should be attached."""
    mock_settings.audit_log_enabled = True
    mock_settings.audit_log_destination = "both"
    mock_settings.audit_log_file = str(tmp_path / "audit.log")
    mock_settings.audit_log_syslog_address = "127.0.0.1:514"
    mock_settings.audit_log_syslog_facility = "local0"
    logger = _fresh_audit_logger()
    configure_audit_logger()
    file_handlers = [h for h in logger.handlers if isinstance(h, _FailClosedFileHandler)]
    syslog_handlers = [h for h in logger.handlers if isinstance(h, _FailClosedSysLogHandler)]
    assert len(file_handlers) >= 1
    assert len(syslog_handlers) >= 1
    logger.handlers = [h for h in logger.handlers if isinstance(h, logging.NullHandler)]


# ---------------------------------------------------------------------------
# _emit and fail-closed behaviour
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.audit.settings")
def test_emit_is_noop_when_disabled(mock_settings: MagicMock) -> None:
    """_emit should return immediately without logging when audit_log_enabled is False."""
    mock_settings.audit_log_enabled = False
    with patch.object(_audit_logger, "info") as mock_info:
        _emit({"event": "test", "value": 1})
        mock_info.assert_not_called()


@patch("netmiko_mcp.audit.settings")
def test_emit_calls_logger_when_enabled(mock_settings: MagicMock) -> None:
    """_emit should call logger.info when audit_log_enabled is True."""
    mock_settings.audit_log_enabled = True
    with patch.object(_audit_logger, "info") as mock_info:
        _emit({"event": "test", "value": 42})
        mock_info.assert_called_once()


@patch("netmiko_mcp.audit.settings")
def test_fail_closed_propagates_handler_error(mock_settings: MagicMock, tmp_path: Path) -> None:
    """A handler error should propagate out of the logger, enforcing fail-closed behaviour.

    Python 3.13 changed Handler.handle() to no longer wrap emit() in a try/except, so
    exceptions propagate as their original type. On earlier Python versions handleError()
    is called and re-raises as RuntimeError. Either way the caller should see an exception
    — the important property is that the error is never silently swallowed.
    """
    mock_settings.audit_log_enabled = True
    mock_settings.audit_log_destination = "file"
    mock_settings.audit_log_file = str(tmp_path / "audit.log")

    formatter = _AuditJsonFormatter()
    handler = _build_file_handler(formatter)

    logger = logging.getLogger("netmiko_mcp.audit.test_fail_closed")
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.INFO)

    with patch.object(handler, "emit", side_effect=OSError("disk full")):
        with pytest.raises((RuntimeError, OSError)):
            logger.info("test", extra={"event": "test"})


# ---------------------------------------------------------------------------
# log_command_attempt
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.audit.settings")
def test_log_command_attempt_writes_json_record(mock_settings: MagicMock, tmp_path: Path) -> None:
    """log_command_attempt should write a valid JSON record to the audit file."""
    log_file = tmp_path / "audit.log"
    mock_settings.audit_log_enabled = True
    mock_settings.audit_log_destination = "file"
    mock_settings.audit_log_file = str(log_file)

    logger = _fresh_audit_logger()
    formatter = _AuditJsonFormatter()
    handler = _build_file_handler(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        log_command_attempt(
            correlation_id="corr-001",
            tool="send_show_command",
            device="router1",
            command="show version",
            verdict=ALLOWED,
            reason=REASON_ALLOWED,
        )
        handler.flush()
    finally:
        logger.handlers = [h for h in logger.handlers if isinstance(h, logging.NullHandler)]

    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["event"] == "command_attempt"
    assert data["correlation_id"] == "corr-001"
    assert data["tool"] == "send_show_command"
    assert data["device"] == "router1"
    assert data["command"] == "show version"
    assert data["verdict"] == ALLOWED
    assert data["reason"] == REASON_ALLOWED


@patch("netmiko_mcp.audit.settings")
def test_log_command_attempt_denied(mock_settings: MagicMock, tmp_path: Path) -> None:
    """log_command_attempt for a denied command should record DENIED verdict and reason."""
    log_file = tmp_path / "audit.log"
    mock_settings.audit_log_enabled = True
    mock_settings.audit_log_destination = "file"
    mock_settings.audit_log_file = str(log_file)

    logger = _fresh_audit_logger()
    formatter = _AuditJsonFormatter()
    handler = _build_file_handler(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        log_command_attempt(
            correlation_id="corr-002",
            tool="send_show_command",
            device="router1",
            command="reload",
            verdict=DENIED,
            reason=REASON_DENY_MATCH,
        )
        handler.flush()
    finally:
        logger.handlers = [h for h in logger.handlers if isinstance(h, logging.NullHandler)]

    data = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert data["verdict"] == DENIED
    assert data["reason"] == REASON_DENY_MATCH


# ---------------------------------------------------------------------------
# log_connection_outcome
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.audit.settings")
def test_log_connection_outcome_success(mock_settings: MagicMock, tmp_path: Path) -> None:
    """log_connection_outcome with OUTCOME_SUCCESS should not include detail or textfsm_parse_failed."""
    log_file = tmp_path / "audit.log"
    mock_settings.audit_log_enabled = True
    mock_settings.audit_log_destination = "file"
    mock_settings.audit_log_file = str(log_file)

    logger = _fresh_audit_logger()
    formatter = _AuditJsonFormatter()
    handler = _build_file_handler(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        log_connection_outcome(
            correlation_id="corr-003",
            tool="send_show_command",
            device="router1",
            command="show version",
            outcome=OUTCOME_SUCCESS,
        )
        handler.flush()
    finally:
        logger.handlers = [h for h in logger.handlers if isinstance(h, logging.NullHandler)]

    data = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert data["event"] == "connection_outcome"
    assert data["outcome"] == OUTCOME_SUCCESS
    assert "detail" not in data
    assert "textfsm_parse_failed" not in data


@patch("netmiko_mcp.audit.settings")
def test_log_connection_outcome_auth_failure_includes_detail(
    mock_settings: MagicMock, tmp_path: Path
) -> None:
    """log_connection_outcome with a detail message should include it in the record."""
    log_file = tmp_path / "audit.log"
    mock_settings.audit_log_enabled = True
    mock_settings.audit_log_destination = "file"
    mock_settings.audit_log_file = str(log_file)

    logger = _fresh_audit_logger()
    formatter = _AuditJsonFormatter()
    handler = _build_file_handler(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        log_connection_outcome(
            correlation_id="corr-004",
            tool="send_show_command",
            device="router1",
            command="show version",
            outcome=OUTCOME_AUTH_FAILURE,
            detail="Invalid credentials",
        )
        handler.flush()
    finally:
        logger.handlers = [h for h in logger.handlers if isinstance(h, logging.NullHandler)]

    data = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert data["outcome"] == OUTCOME_AUTH_FAILURE
    assert data["detail"] == "Invalid credentials"


@patch("netmiko_mcp.audit.settings")
def test_log_connection_outcome_textfsm_parse_failed(
    mock_settings: MagicMock, tmp_path: Path
) -> None:
    """textfsm_parse_failed=True should appear in the record only when set."""
    log_file = tmp_path / "audit.log"
    mock_settings.audit_log_enabled = True
    mock_settings.audit_log_destination = "file"
    mock_settings.audit_log_file = str(log_file)

    logger = _fresh_audit_logger()
    formatter = _AuditJsonFormatter()
    handler = _build_file_handler(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        log_connection_outcome(
            correlation_id="corr-005",
            tool="send_show_command",
            device="router1",
            command="show version",
            outcome=OUTCOME_SUCCESS,
            textfsm_parse_failed=True,
        )
        handler.flush()
    finally:
        logger.handlers = [h for h in logger.handlers if isinstance(h, logging.NullHandler)]

    data = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert data.get("textfsm_parse_failed") is True


# ---------------------------------------------------------------------------
# log_tool_invocation
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.audit.settings")
def test_log_tool_invocation_ping(mock_settings: MagicMock, tmp_path: Path) -> None:
    """log_tool_invocation for ping should write a record with empty arguments."""
    log_file = tmp_path / "audit.log"
    mock_settings.audit_log_enabled = True
    mock_settings.audit_log_destination = "file"
    mock_settings.audit_log_file = str(log_file)

    logger = _fresh_audit_logger()
    formatter = _AuditJsonFormatter()
    handler = _build_file_handler(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        log_tool_invocation(tool="ping", arguments={})
        handler.flush()
    finally:
        logger.handlers = [h for h in logger.handlers if isinstance(h, logging.NullHandler)]

    data = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert data["event"] == "tool_invocation"
    assert data["tool"] == "ping"
    assert data["arguments"] == {}


@patch("netmiko_mcp.audit.settings")
def test_log_tool_invocation_read_device_output(mock_settings: MagicMock, tmp_path: Path) -> None:
    """log_tool_invocation for read_device_output should include device_name and filename."""
    log_file = tmp_path / "audit.log"
    mock_settings.audit_log_enabled = True
    mock_settings.audit_log_destination = "file"
    mock_settings.audit_log_file = str(log_file)

    logger = _fresh_audit_logger()
    formatter = _AuditJsonFormatter()
    handler = _build_file_handler(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        log_tool_invocation(
            tool="read_device_output",
            arguments={"device_name": "router1", "filename": "show_version_20260608.txt"},
        )
        handler.flush()
    finally:
        logger.handlers = [h for h in logger.handlers if isinstance(h, logging.NullHandler)]

    data = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert data["tool"] == "read_device_output"
    assert data["arguments"]["device_name"] == "router1"
    assert data["arguments"]["filename"] == "show_version_20260608.txt"


# ---------------------------------------------------------------------------
# save_channel_transcript
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.audit.settings")
def test_save_channel_transcript_creates_file(mock_settings: MagicMock, tmp_path: Path) -> None:
    """save_channel_transcript should write the decoded transcript to a file."""
    mock_settings.audit_log_transcript_dir = str(tmp_path / "transcripts")

    raw = b"router1#show version\r\nCisco IOS ...\r\nrouter1#"
    save_channel_transcript("corr-abc", "router1", raw)

    transcript_dir = tmp_path / "transcripts"
    files = list(transcript_dir.glob("*.txt"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "show version" in content
    assert "corr-abc" in files[0].name
    assert "router1" in files[0].name


@patch("netmiko_mcp.audit.settings")
def test_save_channel_transcript_permissions(mock_settings: MagicMock, tmp_path: Path) -> None:
    """Transcript directory should be 0o700 and file should be 0o600."""
    mock_settings.audit_log_transcript_dir = str(tmp_path / "transcripts")

    save_channel_transcript("corr-xyz", "router1", b"output")
    transcript_dir = tmp_path / "transcripts"
    files = list(transcript_dir.glob("*.txt"))
    assert oct(transcript_dir.stat().st_mode & 0o777) == oct(0o700)
    assert oct(files[0].stat().st_mode & 0o777) == oct(0o600)


@patch("netmiko_mcp.audit.settings")
def test_save_channel_transcript_sanitises_device_name(
    mock_settings: MagicMock, tmp_path: Path
) -> None:
    """Unusual characters in device_name should be replaced with underscores."""
    mock_settings.audit_log_transcript_dir = str(tmp_path / "transcripts")

    save_channel_transcript("corr-zzz", "router/1:weird", b"output")
    files = list((tmp_path / "transcripts").glob("*.txt"))
    assert len(files) == 1
    assert "/" not in files[0].name
    assert ":" not in files[0].name


# ---------------------------------------------------------------------------
# _build_syslog_handler address parsing
# ---------------------------------------------------------------------------


def test_build_syslog_handler_host_port() -> None:
    """A 'host:port' address string should be parsed into a (host, int) tuple."""
    from netmiko_mcp.audit import _build_syslog_handler

    with patch("netmiko_mcp.audit.settings") as mock_settings:
        mock_settings.audit_log_syslog_address = "192.168.1.1:514"
        mock_settings.audit_log_syslog_facility = "local0"
        with patch("netmiko_mcp.audit._FailClosedSysLogHandler") as MockHandler:
            _build_syslog_handler(_AuditJsonFormatter())
            call_kwargs = MockHandler.call_args
            assert call_kwargs is not None
            address_arg = call_kwargs.kwargs.get("address") or call_kwargs.args[0]
            assert address_arg == ("192.168.1.1", 514)


def test_build_syslog_handler_unix_socket() -> None:
    """A UNIX socket path should be passed as a string, not parsed as host:port."""
    from netmiko_mcp.audit import _build_syslog_handler

    with patch("netmiko_mcp.audit.settings") as mock_settings:
        mock_settings.audit_log_syslog_address = "/dev/log"
        mock_settings.audit_log_syslog_facility = "local0"
        with patch("netmiko_mcp.audit._FailClosedSysLogHandler") as MockHandler:
            _build_syslog_handler(_AuditJsonFormatter())
            call_kwargs = MockHandler.call_args
            assert call_kwargs is not None
            address_arg = call_kwargs.kwargs.get("address") or call_kwargs.args[0]
            assert address_arg == "/dev/log"


# ---------------------------------------------------------------------------
# CommandAuditContext
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.audit.log_command_attempt")
def test_command_audit_context_log_attempt(mock_log_attempt: MagicMock) -> None:
    """log_attempt should delegate to log_command_attempt with all context fields."""
    from netmiko_mcp.audit import ALLOWED, CommandAuditContext

    audit_context = CommandAuditContext(
        correlation_id="corr-123",
        tool="send_show_command",
        device="rtr1",
        command="show version",
    )
    audit_context.log_attempt(ALLOWED, "ALLOWED")

    mock_log_attempt.assert_called_once_with(
        correlation_id="corr-123",
        tool="send_show_command",
        device="rtr1",
        command="show version",
        verdict=ALLOWED,
        reason="ALLOWED",
    )


@patch("netmiko_mcp.audit.log_connection_outcome")
def test_command_audit_context_log_outcome_minimal(mock_log_outcome: MagicMock) -> None:
    """log_outcome with only outcome should call log_connection_outcome with correct defaults."""
    from netmiko_mcp.audit import OUTCOME_SUCCESS, CommandAuditContext

    audit_context = CommandAuditContext(
        correlation_id="corr-123",
        tool="send_show_command",
        device="rtr1",
        command="show version",
    )
    audit_context.log_outcome(OUTCOME_SUCCESS)

    mock_log_outcome.assert_called_once_with(
        correlation_id="corr-123",
        tool="send_show_command",
        device="rtr1",
        command="show version",
        outcome=OUTCOME_SUCCESS,
        detail=None,
        textfsm_parse_failed=False,
    )


@patch("netmiko_mcp.audit.log_connection_outcome")
def test_command_audit_context_log_outcome_with_detail(mock_log_outcome: MagicMock) -> None:
    """log_outcome with detail should forward it to log_connection_outcome."""
    from netmiko_mcp.audit import OUTCOME_ERROR, CommandAuditContext

    audit_context = CommandAuditContext(
        correlation_id="corr-123",
        tool="send_show_command",
        device="rtr1",
        command="show version",
    )
    audit_context.log_outcome(OUTCOME_ERROR, detail="Traceback (most recent call last)...")

    mock_log_outcome.assert_called_once_with(
        correlation_id="corr-123",
        tool="send_show_command",
        device="rtr1",
        command="show version",
        outcome=OUTCOME_ERROR,
        detail="Traceback (most recent call last)...",
        textfsm_parse_failed=False,
    )


@patch("netmiko_mcp.audit.log_connection_outcome")
def test_command_audit_context_log_outcome_textfsm_parse_failed(
    mock_log_outcome: MagicMock,
) -> None:
    """log_outcome with textfsm_parse_failed=True should forward it to log_connection_outcome."""
    from netmiko_mcp.audit import OUTCOME_SUCCESS, CommandAuditContext

    audit_context = CommandAuditContext(
        correlation_id="corr-123",
        tool="send_show_command",
        device="rtr1",
        command="show version",
    )
    audit_context.log_outcome(OUTCOME_SUCCESS, textfsm_parse_failed=True)

    mock_log_outcome.assert_called_once_with(
        correlation_id="corr-123",
        tool="send_show_command",
        device="rtr1",
        command="show version",
        outcome=OUTCOME_SUCCESS,
        detail=None,
        textfsm_parse_failed=True,
    )

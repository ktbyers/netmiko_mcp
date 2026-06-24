from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from netmiko_mcp.audit import (
    REASON_ALLOWED,
    REASON_DENY_MATCH,
    REASON_INVALID_PIPE_MODIFIER,
    REASON_MULTIPLE_PIPES,
    REASON_NO_ALLOW_MATCH,
    REASON_UNSAFE_CHAR,
)
from netmiko_mcp.security import (
    ValidationResult,
    glob_to_regex,
    load_commands,
    validate_command,
)


# ---------------------------------------------------------------------------
# glob_to_regex
# ---------------------------------------------------------------------------


def test_glob_to_regex_exact_match() -> None:
    """A pattern with no wildcard must match only the exact string."""
    p = glob_to_regex("show version")
    assert p.match("show version")
    assert not p.match("show version extra")
    assert not p.match("show versio")
    assert not p.match("")


def test_glob_to_regex_trailing_wildcard_matches_arguments() -> None:
    """'show *' must match 'show' with any safe arguments."""
    p = glob_to_regex("show *")
    assert p.match("show version")
    assert p.match("show ip interface brief")
    assert p.match("show bgp summary")


def test_glob_to_regex_trailing_wildcard_matches_bare_command() -> None:
    """'show *' must also match 'show' with no arguments (the group is optional)."""
    p = glob_to_regex("show *")
    assert p.match("show")


def test_glob_to_regex_is_case_insensitive() -> None:
    """Patterns must match regardless of capitalisation."""
    p = glob_to_regex("show version")
    assert p.match("Show Version")
    assert p.match("SHOW VERSION")


def test_glob_to_regex_strips_leading_trailing_whitespace() -> None:
    """Leading/trailing whitespace in the pattern must be ignored."""
    p = glob_to_regex("  show version  ")
    assert p.match("show version")


def test_glob_to_regex_trailing_wildcard_with_multiword_prefix() -> None:
    """A trailing wildcard after a multi-word prefix anchors that prefix strictly."""
    p = glob_to_regex("show ip *")
    assert p.match("show ip interface brief")
    assert p.match("show ip route")
    assert p.match("show ip")  # bare — wildcard group is optional
    assert not p.match("show version")  # wrong prefix
    assert not p.match("show ipv6 route")  # 'ipv6' != 'ip'


def test_glob_to_regex_regex_special_chars_in_pattern_are_neutralised() -> None:
    """Regex special characters in the literal part of a pattern must be treated
    as plain text, not as regex operators."""
    p = glob_to_regex("show version (detail)")
    assert p.match("show version (detail)")
    assert not p.match("show version Xdetail)")


def test_glob_to_regex_wildcard_does_not_match_empty_with_mandatory_prefix() -> None:
    """A pattern like 'show *' must not match an unrelated command."""
    p = glob_to_regex("show *")
    assert not p.match("configure terminal")
    assert not p.match("debug ip packet")


# ---------------------------------------------------------------------------
# load_commands
# ---------------------------------------------------------------------------


def test_load_commands_file_not_found(tmp_path: Path) -> None:
    """load_commands returns {} when the command_file path does not exist."""
    load_commands.cache_clear()
    non_existent = tmp_path / "no_such_commands.yml"
    with patch("netmiko_mcp.security.settings") as mock_settings:
        mock_settings.command_file = str(non_existent)
        result = load_commands()
    load_commands.cache_clear()
    assert result == {}


def test_load_commands_valid_file(tmp_path: Path) -> None:
    """load_commands returns the parsed YAML dict when the file exists."""
    load_commands.cache_clear()
    cfg = tmp_path / "commands.yml"
    cfg.write_text(
        'allowed_commands: ["show version"]\ndenied_commands: ["reload"]\n',
        encoding="utf-8",
    )
    with patch("netmiko_mcp.security.settings") as mock_settings:
        mock_settings.command_file = str(cfg)
        result = load_commands()
    load_commands.cache_clear()
    assert result["allowed_commands"] == ["show version"]
    assert result["denied_commands"] == ["reload"]


def test_load_commands_result_is_cached(tmp_path: Path) -> None:
    """load_commands should only read the file once across multiple calls."""
    load_commands.cache_clear()
    cfg = tmp_path / "commands.yml"
    cfg.write_text('allowed_commands: ["show version"]\n', encoding="utf-8")
    with patch("netmiko_mcp.security.settings") as mock_settings:
        mock_settings.command_file = str(cfg)
        with patch("netmiko_mcp.security.load_yaml_file") as mock_yaml:
            mock_yaml.return_value = {"allowed_commands": ["show version"]}
            load_commands()
            load_commands()
            load_commands()
    load_commands.cache_clear()
    mock_yaml.assert_called_once()


@patch("netmiko_mcp.security.load_commands")
def test_validate_command_default_allowed(mock_load: Any) -> None:
    """Test that default behavior strictly denies everything if no YAML is loaded."""
    mock_load.return_value = {}  # Simulate missing or empty YAML
    assert not validate_command("show ip int brief").allowed
    assert not validate_command("show version").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_default_denied(mock_load: Any, mock_settings: Any) -> None:
    """Test that commands are denied by default when no whitelist is configured."""
    mock_load.return_value = {}  # Simulate missing or empty commands file
    mock_settings.allow_pipe = False
    mock_settings.allowed_command_chars = (
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ./:_-,"
    )

    # Pipes are blocked when allow_pipe is False
    assert not validate_command("show run | include password").allowed
    # Nothing is allowed without a whitelist
    assert not validate_command("clear ip ospf process").allowed
    assert not validate_command("debug ip packet").allowed


@patch("netmiko_mcp.security.load_commands")
def test_validate_command_custom_yaml(mock_load: Any) -> None:
    """Test that an external YAML config overrides the defaults."""
    mock_load.return_value = {
        "allowed_commands": ["display interface brief", "show version"],
        "denied_commands": ["reboot"],
    }

    # Defaults should now fail (if they aren't explicitly in the custom config)
    assert not validate_command("show ip int brief").allowed

    # Custom allowed should pass
    assert validate_command("display interface brief").allowed

    # Custom denied should fail
    assert not validate_command("display interface brief reboot").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_pipes_disabled(mock_load: Any, mock_settings: Any) -> None:
    """Test that pipes are rejected when allow_pipe is False."""
    mock_settings.allow_pipe = False
    mock_settings.allowed_command_chars = (
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ./:_-,"
    )
    mock_settings.pipe_modifiers = ["include", "exclude", "section", "begin", "count"]
    mock_load.return_value = {"allowed_commands": ["show version"], "denied_commands": []}

    # Base command passes
    assert validate_command("show version").allowed
    # Piped command fails
    assert not validate_command("show version | include uptime").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_pipes_enabled_safe(mock_load: Any, mock_settings: Any) -> None:
    """Test that safe pipes are permitted when allow_pipe is True."""
    mock_settings.allow_pipe = True
    mock_settings.allowed_command_chars = (
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ./:_-,"
    )
    # Simulate a user who has added IOS and NX-OS modifiers to their config
    mock_settings.pipe_modifiers = [
        "include",
        "exclude",
        "section",
        "begin",
        "count",
        "grep",
        "egrep",
        "head",
        "last",
        "less",
        "no-more",
        "sort",
        "uniq",
        "wc",
        "json",
        "json-pretty",
        "xml",
        "xmlin",
        "xmlout",
        "human",
        "end",
        "nz",
    ]
    mock_load.return_value = {"allowed_commands": ["show version"], "denied_commands": []}

    # Default IOS/IOS-XE modifiers
    assert validate_command("show version | include uptime").allowed
    assert validate_command("show version | exclude test").allowed
    assert validate_command("show version | section ospf").allowed
    assert validate_command("show version | begin router").allowed
    assert validate_command("show version | count").allowed

    # NX-OS formatting pipes
    assert validate_command("show version | json").allowed
    assert validate_command("show version | json-pretty").allowed
    assert validate_command("show version | xml").allowed
    assert validate_command("show version | human").allowed

    # NX-OS textual pipes
    assert validate_command("show version | grep test").allowed
    assert validate_command("show version | egrep test").allowed
    assert validate_command("show version | head 5").allowed
    assert validate_command("show version | last 5").allowed
    assert validate_command("show version | sort").allowed
    assert validate_command("show version | uniq").allowed
    assert validate_command("show version | wc").allowed
    assert validate_command("show version | end test").allowed
    assert validate_command("show version | nz").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_pipes_enabled_dangerous(mock_load: Any, mock_settings: Any) -> None:
    """Test that dangerous pipes are rejected even when allow_pipe is True."""
    mock_settings.allow_pipe = True
    mock_settings.allowed_command_chars = (
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ./:_-,"
    )
    mock_settings.pipe_modifiers = ["include", "exclude", "section", "begin", "count"]
    mock_load.return_value = {"allowed_commands": ["show version"], "denied_commands": []}

    # Dangerous redirects
    assert not validate_command("show version | redirect tftp://1.1.1.1/test").allowed
    assert not validate_command("show version | append flash:test.txt").allowed
    assert not validate_command("show version | tee http://bad.com").allowed

    # Dangerous shell escapes and manipulations (NX-OS)
    assert not validate_command("show version | awk '{print $1}'").allowed
    assert not validate_command("show version | sed 's/a/b/'").allowed
    assert not validate_command("show version | cut -d' ' -f1").allowed
    assert not validate_command("show version | tr a b").allowed
    assert not validate_command("show version | vsh").allowed
    assert not validate_command("show version | email test@test.com").allowed
    assert not validate_command("show version | diff").allowed


# ---------------------------------------------------------------------------
# validate_command — comprehensive rule verification
# ---------------------------------------------------------------------------

# Shared config used across all comprehensive tests.
_VC_ALLOWED = [
    "show version",
    "show ip interface brief",
    "show ip route *",
    "show bgp *",
    "show interfaces *",
    "display *",
]
_VC_DENIED = [
    "configure *",
    "reload",
    "debug *",
    "clear *",
]
_VC_PIPE_MODIFIERS = ["include", "exclude", "section", "begin", "count"]
_VC_ALLOWED_COMMAND_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ./:_-,"


def _vc_setup(mock_load: Any, mock_settings: Any, allow_pipe: bool = False) -> None:
    """Configure standard mocks for comprehensive validate_command tests."""
    mock_load.return_value = {
        "allowed_commands": _VC_ALLOWED,
        "denied_commands": _VC_DENIED,
    }
    mock_settings.allow_pipe = allow_pipe
    mock_settings.allowed_command_chars = _VC_ALLOWED_COMMAND_CHARS
    mock_settings.pipe_modifiers = _VC_PIPE_MODIFIERS


# --- Rule 4: unsafe characters blocked before anything else -----------------


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule4_semicolon_blocked(mock_load: Any, mock_settings: Any) -> None:
    """Rule 4: Commands containing ';' are unconditionally rejected."""
    _vc_setup(mock_load, mock_settings)
    assert not validate_command("show version; reload").allowed
    assert not validate_command("show version;reload").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule4_newline_blocked(mock_load: Any, mock_settings: Any) -> None:
    """Rule 4: Commands containing a newline are unconditionally rejected."""
    _vc_setup(mock_load, mock_settings)
    assert not validate_command("show version\nreload").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule4_carriage_return_blocked(mock_load: Any, mock_settings: Any) -> None:
    """Rule 4: Commands containing a carriage return are unconditionally rejected."""
    _vc_setup(mock_load, mock_settings)
    assert not validate_command("show version\rreload").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule4_ampersand_blocked(mock_load: Any, mock_settings: Any) -> None:
    """Rule 4: Commands containing '&' are unconditionally rejected."""
    _vc_setup(mock_load, mock_settings)
    assert not validate_command("show version && reload").allowed
    assert not validate_command("show version &").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule4_unsafe_char_in_allowed_command_still_blocked(
    mock_load: Any, mock_settings: Any
) -> None:
    """Rule 4: Unsafe chars are rejected even if the base command is in allowed_commands."""
    _vc_setup(mock_load, mock_settings)
    assert not validate_command("show version; show version").allowed


# --- Rule 1: denied_commands takes precedence --------------------------------


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule1_exact_deny(mock_load: Any, mock_settings: Any) -> None:
    """Rule 1: A plain denied string matches only that exact command."""
    _vc_setup(mock_load, mock_settings)
    assert not validate_command("reload").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule1_exact_deny_no_substring_match(mock_load: Any, mock_settings: Any) -> None:
    """Rule 1: Exact deny 'reload' must NOT block commands that merely contain 'reload'."""
    mock_load.return_value = {
        "allowed_commands": _VC_ALLOWED + ["show reload-cause"],
        "denied_commands": ["reload"],
    }
    mock_settings.allow_pipe = False
    mock_settings.allowed_command_chars = _VC_ALLOWED_COMMAND_CHARS
    mock_settings.pipe_modifiers = _VC_PIPE_MODIFIERS
    assert validate_command("show reload-cause").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule1_glob_deny(mock_load: Any, mock_settings: Any) -> None:
    """Rule 1: Glob denied patterns block all matching commands."""
    _vc_setup(mock_load, mock_settings)
    assert not validate_command("configure terminal").allowed
    assert not validate_command("configure replace flash:cfg").allowed
    assert not validate_command("configure").allowed
    assert not validate_command("debug ip packet").allowed
    assert not validate_command("debug ip ospf adj").allowed
    assert not validate_command("clear ip ospf process").allowed
    assert not validate_command("clear counters").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule1_denied_beats_allowed(mock_load: Any, mock_settings: Any) -> None:
    """Rule 1: denied_commands always takes precedence over allowed_commands."""
    mock_load.return_value = {
        "allowed_commands": _VC_ALLOWED + ["configure *"],
        "denied_commands": _VC_DENIED,
    }
    mock_settings.allow_pipe = False
    mock_settings.allowed_command_chars = _VC_ALLOWED_COMMAND_CHARS
    mock_settings.pipe_modifiers = _VC_PIPE_MODIFIERS
    assert not validate_command("configure terminal").allowed


# --- Rule 2: allowed_commands -----------------------------------------------


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule2_exact_match(mock_load: Any, mock_settings: Any) -> None:
    """Rule 2: Exact allowed commands pass."""
    _vc_setup(mock_load, mock_settings)
    assert validate_command("show version").allowed
    assert validate_command("show ip interface brief").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule2_case_insensitive(mock_load: Any, mock_settings: Any) -> None:
    """Rule 2: Allow matching is case-insensitive."""
    _vc_setup(mock_load, mock_settings)
    assert validate_command("SHOW VERSION").allowed
    assert validate_command("Show Version").allowed
    assert validate_command("SHOW IP INTERFACE BRIEF").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule2_glob_with_args(mock_load: Any, mock_settings: Any) -> None:
    """Rule 2: Glob patterns match commands with arguments."""
    _vc_setup(mock_load, mock_settings)
    assert validate_command("show ip route 10.0.0.0 255.0.0.0").allowed
    assert validate_command("show bgp summary").allowed
    assert validate_command("show bgp neighbors 10.0.0.1").allowed
    assert validate_command("show interfaces GigabitEthernet0/0").allowed
    assert validate_command("display version").allowed
    assert validate_command("display interface brief").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule2_glob_bare_command(mock_load: Any, mock_settings: Any) -> None:
    """Rule 2: Glob patterns also match the bare command with no arguments."""
    _vc_setup(mock_load, mock_settings)
    assert validate_command("show ip route").allowed
    assert validate_command("show bgp").allowed
    assert validate_command("display").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule2_not_in_allowed(mock_load: Any, mock_settings: Any) -> None:
    """Rule 2: Commands not in allowed_commands are rejected."""
    _vc_setup(mock_load, mock_settings)
    assert not validate_command("show running-config").allowed
    assert not validate_command("show startup-config").allowed
    assert not validate_command("ping 10.0.0.1").allowed
    assert not validate_command("traceroute 10.0.0.1").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule2_abbreviations_rejected(mock_load: Any, mock_settings: Any) -> None:
    """Rule 2: Command abbreviations are not permitted."""
    _vc_setup(mock_load, mock_settings)
    assert not validate_command("sh ver").allowed
    assert not validate_command("sh ip int br").allowed


# --- Rule 3: pipe handling --------------------------------------------------


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule3_pipe_disabled(mock_load: Any, mock_settings: Any) -> None:
    """Rule 3: Any pipe is rejected when allow_pipe is False."""
    _vc_setup(mock_load, mock_settings, allow_pipe=False)
    assert not validate_command("show version | include IOS").allowed
    assert not validate_command("show bgp summary | include Active").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule3_pipe_valid_modifier(mock_load: Any, mock_settings: Any) -> None:
    """Rule 3: Valid pipe modifier passes when allow_pipe is True."""
    _vc_setup(mock_load, mock_settings, allow_pipe=True)
    assert validate_command("show version | include IOS").allowed
    assert validate_command("show version | exclude uptime").allowed
    assert validate_command("show version | section ospf").allowed
    assert validate_command("show version | begin router").allowed
    assert validate_command("show version | count").allowed
    assert validate_command("show bgp neighbors | include Active").allowed
    assert validate_command("show interfaces GigabitEthernet0/0 | include rate").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule3_pipe_invalid_modifier(mock_load: Any, mock_settings: Any) -> None:
    """Rule 3: Pipe modifier not in pipe_modifiers is rejected."""
    _vc_setup(mock_load, mock_settings, allow_pipe=True)
    assert not validate_command("show version | grep IOS").allowed
    assert not validate_command("show version | awk '{print $1}'").allowed
    assert not validate_command("show version | redirect tftp://1.1.1.1").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule3_bare_pipe_blocked(mock_load: Any, mock_settings: Any) -> None:
    """Rule 3: A trailing pipe with nothing after it is rejected."""
    _vc_setup(mock_load, mock_settings, allow_pipe=True)
    assert not validate_command("show version |").allowed
    assert not validate_command("show version |   ").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule3_multiple_pipes_blocked(mock_load: Any, mock_settings: Any) -> None:
    """Rule 3: Multiple pipes in a single command are rejected."""
    _vc_setup(mock_load, mock_settings, allow_pipe=True)
    assert not validate_command("show version | include IOS | count").allowed
    assert not validate_command("show bgp summary | include Active | section peer").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule3_pipe_base_command_validated(mock_load: Any, mock_settings: Any) -> None:
    """Rule 3: The base command before the pipe must still be in allowed_commands."""
    _vc_setup(mock_load, mock_settings, allow_pipe=True)
    assert not validate_command("show running-config | include interface").allowed
    assert validate_command("show version | include IOS").allowed


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_vc_rule3_denied_base_command_with_pipe_blocked(mock_load: Any, mock_settings: Any) -> None:
    """Rule 3: A denied base command is still blocked even with a valid pipe."""
    _vc_setup(mock_load, mock_settings, allow_pipe=True)
    assert not validate_command("configure terminal | include ip").allowed
    assert not validate_command("debug ip packet | include error").allowed


# ---------------------------------------------------------------------------
# ValidationResult — structure and reason codes
# ---------------------------------------------------------------------------


def test_validation_result_dataclass_fields() -> None:
    """ValidationResult should expose allowed and reason attributes."""
    r = ValidationResult(allowed=True, reason=REASON_ALLOWED)
    assert r.allowed is True
    assert r.reason == REASON_ALLOWED


def test_validation_result_denied() -> None:
    r = ValidationResult(allowed=False, reason=REASON_NO_ALLOW_MATCH)
    assert r.allowed is False
    assert r.reason == REASON_NO_ALLOW_MATCH


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_reason_unsafe_char(mock_load: Any, mock_settings: Any) -> None:
    """A command with an unsafe character should return REASON_UNSAFE_CHAR."""
    _vc_setup(mock_load, mock_settings)
    result = validate_command("show version; reload")
    assert not result.allowed
    assert result.reason == REASON_UNSAFE_CHAR


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_reason_deny_match(mock_load: Any, mock_settings: Any) -> None:
    """A command matching denied_commands should return REASON_DENY_MATCH."""
    _vc_setup(mock_load, mock_settings)
    result = validate_command("reload")
    assert not result.allowed
    assert result.reason == REASON_DENY_MATCH


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_reason_pipe_not_allowed(mock_load: Any, mock_settings: Any) -> None:
    """A piped command when allow_pipe=False is rejected at the allowlist check
    since '|' is only in effective_allowed when allow_pipe is True."""
    _vc_setup(mock_load, mock_settings, allow_pipe=False)
    result = validate_command("show version | include IOS")
    assert not result.allowed
    assert result.reason == REASON_UNSAFE_CHAR


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_reason_multiple_pipes(mock_load: Any, mock_settings: Any) -> None:
    """Multiple pipes should return REASON_MULTIPLE_PIPES."""
    _vc_setup(mock_load, mock_settings, allow_pipe=True)
    result = validate_command("show version | include IOS | count")
    assert not result.allowed
    assert result.reason == REASON_MULTIPLE_PIPES


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_reason_invalid_pipe_modifier(mock_load: Any, mock_settings: Any) -> None:
    """An unsupported pipe modifier should return REASON_INVALID_PIPE_MODIFIER."""
    _vc_setup(mock_load, mock_settings, allow_pipe=True)
    result = validate_command("show version | grep IOS")
    assert not result.allowed
    assert result.reason == REASON_INVALID_PIPE_MODIFIER


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_reason_invalid_pipe_modifier_bare_pipe(
    mock_load: Any, mock_settings: Any
) -> None:
    """A trailing pipe with no modifier should return REASON_INVALID_PIPE_MODIFIER."""
    _vc_setup(mock_load, mock_settings, allow_pipe=True)
    result = validate_command("show version |")
    assert not result.allowed
    assert result.reason == REASON_INVALID_PIPE_MODIFIER


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_reason_no_allow_match(mock_load: Any, mock_settings: Any) -> None:
    """A command not in allowed_commands should return REASON_NO_ALLOW_MATCH."""
    _vc_setup(mock_load, mock_settings)
    result = validate_command("show running-config")
    assert not result.allowed
    assert result.reason == REASON_NO_ALLOW_MATCH


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_reason_allowed(mock_load: Any, mock_settings: Any) -> None:
    """An allowed command should return REASON_ALLOWED."""
    _vc_setup(mock_load, mock_settings)
    result = validate_command("show version")
    assert result.allowed
    assert result.reason == REASON_ALLOWED


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_unsafe_char_takes_precedence_over_deny(
    mock_load: Any, mock_settings: Any
) -> None:
    """UNSAFE_CHAR should be reported before DENY_MATCH even if the command also matches denied."""
    _vc_setup(mock_load, mock_settings)
    result = validate_command("reload; rm -rf /")
    assert not result.allowed
    assert result.reason == REASON_UNSAFE_CHAR


# ---------------------------------------------------------------------------
# Deny carve-out bypass scenarios
# allowed: ["show *"], denied: ["show version"]
# Each case should be denied. Cases marked BYPASS are known to slip through today.
# ---------------------------------------------------------------------------

_CARVEOUT_ALLOWED = ["show *"]
_CARVEOUT_DENIED = ["show version"]


@pytest.mark.parametrize(
    "command,expected_allowed",
    [
        ("show version", False),  # exact match — denied correctly today
        ("SHOW VERSION", False),  # all caps
        ("Show Version", False),  # mixed case
        (" show version", False),  # leading space — BYPASS
        ("show version ", False),  # trailing space — BYPASS
        ("\tshow version", False),  # leading tab — BYPASS
        ("show  version", False),  # double space — BYPASS
        ("show\tversion", False),  # internal tab — BYPASS
        ("show\xa0version", False),  # NBSP (U+00A0) — BYPASS
        ("show\u3000version", False),  # ideographic space (U+3000) — BYPASS
        ("show\x0bversion", False),  # vertical tab (U+000B) — BYPASS
        (
            "show version\tshow ip interface brief",
            True,
        ),  # tab-chained: normalizes to invalid cmd, not 'show version'
    ],
)
@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_deny_carveout_bypass(
    mock_load: Any, mock_settings: Any, command: str, expected_allowed: bool
) -> None:
    """A broad allow-list with a specific deny carve-out should block cosmetic
    variants of the denied command. Cases that currently bypass the deny check
    are included to document the known failure modes."""
    mock_load.return_value = {
        "allowed_commands": _CARVEOUT_ALLOWED,
        "denied_commands": _CARVEOUT_DENIED,
    }
    mock_settings.allow_pipe = False
    mock_settings.allowed_command_chars = _VC_ALLOWED_COMMAND_CHARS
    mock_settings.pipe_modifiers = _VC_PIPE_MODIFIERS

    result = validate_command(command)
    assert result.allowed == expected_allowed


# ---------------------------------------------------------------------------
# Pipe bypass: deny check runs on full command string, not base command
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command,expected_allowed",
    [
        ("show version | include Cisco", False),  # BYPASS: pipe with spaces
        ("show version|include Cisco", False),  # BYPASS: pipe with no spaces
        ("show version | count", False),  # BYPASS: count modifier
    ],
)
@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_deny_carveout_pipe_bypass(
    mock_load: Any, mock_settings: Any, command: str, expected_allowed: bool
) -> None:
    """With allow_pipe=True, the deny check runs against the full command string
    including the pipe segment. A denied base command with a valid pipe modifier
    currently slips through because the full string does not match the deny pattern."""
    mock_load.return_value = {
        "allowed_commands": _CARVEOUT_ALLOWED,
        "denied_commands": _CARVEOUT_DENIED,
    }
    mock_settings.allow_pipe = True
    mock_settings.allowed_command_chars = _VC_ALLOWED_COMMAND_CHARS
    mock_settings.pipe_modifiers = _VC_PIPE_MODIFIERS

    result = validate_command(command)
    assert result.allowed == expected_allowed


# ---------------------------------------------------------------------------
# Allowlist character rejection
# Characters caught by the allowlist check (REASON_UNSAFE_CHAR).
# Note: Python 3's str.split() (no args) treats all Unicode whitespace as
# whitespace — including NBSP (\xa0), ideographic space (\u3000), tab,
# newline, vertical tab, etc. — so those are normalized to spaces before
# reaching the allowlist check. The allowlist catches non-whitespace special
# characters that survive normalization.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "show version; reload",  # semicolon — not whitespace, not in allowlist
        "show version & reload",  # ampersand — not whitespace, not in allowlist
    ],
)
@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_allowlist_rejects_disallowed_chars(
    mock_load: Any, mock_settings: Any, command: str
) -> None:
    """Characters not in allowed_command_chars must be rejected with
    REASON_UNSAFE_CHAR before any deny/allow matching."""
    _vc_setup(mock_load, mock_settings)
    result = validate_command(command)
    assert not result.allowed
    assert result.reason == REASON_UNSAFE_CHAR


# ---------------------------------------------------------------------------
# Pipe auto-add: '|' in effective_allowed only when allow_pipe=True
# ---------------------------------------------------------------------------


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_pipe_char_allowed_when_allow_pipe_true(mock_load: Any, mock_settings: Any) -> None:
    """'|' is not in allowed_command_chars but must pass the character check
    when allow_pipe=True because it is added to the effective allowed set."""
    _vc_setup(mock_load, mock_settings, allow_pipe=True)
    assert "|" not in mock_settings.allowed_command_chars
    result = validate_command("show version | include IOS")
    assert result.allowed
    assert result.reason == REASON_ALLOWED


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_pipe_char_rejected_when_allow_pipe_false(mock_load: Any, mock_settings: Any) -> None:
    """'|' must be rejected by the allowlist check (REASON_UNSAFE_CHAR) when
    allow_pipe=False because it is not added to the effective allowed set."""
    _vc_setup(mock_load, mock_settings, allow_pipe=False)
    result = validate_command("show version | include IOS")
    assert not result.allowed
    assert result.reason == REASON_UNSAFE_CHAR


# ---------------------------------------------------------------------------
# normalized_command: whitespace collapsed, capitalization preserved
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command,expected_normalized",
    [
        ("show version", "show version"),  # already clean
        ("Show   Version", "Show Version"),  # caps preserved, spaces collapsed
        ("  show version  ", "show version"),  # leading/trailing stripped
        ("SHOW\tVERSION", "SHOW VERSION"),  # tab normalized, caps preserved
        ("show  ip  route", "show ip route"),  # multiple internal spaces
    ],
)
@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_normalized_command_in_result(
    mock_load: Any, mock_settings: Any, command: str, expected_normalized: str
) -> None:
    """normalized_command in ValidationResult must reflect whitespace-collapsed,
    capitalization-preserved form regardless of allowed/denied outcome."""
    _vc_setup(mock_load, mock_settings)
    result = validate_command(command)
    assert result.normalized_command == expected_normalized

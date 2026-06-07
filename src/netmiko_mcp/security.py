"""
Security validation and command verification layer for the Netmiko MCP server.

Rules:
1. Default Deny: Nothing is allowed unless it is added the whitelist (allowed_commands).
   The whitelist is empty be default.
2. The blacklist (denied_commands) has precedence over the whitelist so if both
   blacklist and whitelist match a given command, then the command is denied.
3. Pipes are denied by default. Multi-command injection vectors (e.g. `;`, `\n`, `\r`,
   `&`) are blocked via the unsafe_chars check before any other validation.
4. Every attempted and executed command must be logged for audit and compliance.
   This should include the reason for acceptance or rejection. [FIX]
5. Configuration changes are disallowed by default, both at the Netmiko-level
   (no send_config_set) and at the command-validation level.
6. Globbing should be supported ("show *") in both the whitelist and in the blacklist.
   This will be converted over to regular expressions in the Python code.

Questions:
1. How to handle the command abbreviation issue?
2. Should we support explicit regular expressions in allowed/denied list?
"""

import re
from pathlib import Path
from typing import Any

from netmiko_mcp.config import settings
from netmiko.utilities import load_yaml_file

# Default fallback if no custom configuration is provided.
# We default to strictly denying everything. Users MUST provide a YAML configuration
# file to allow commands.
DEFAULT_ALLOWED_COMMANDS: list[str] = []
DEFAULT_DENIED_COMMANDS: list[str] = []


def _to_regex_char(c: str) -> str:
    """Return the regex character class representation of a single character.
    Non-printable characters (e.g. newline, carriage return) are converted to
    their escaped forms (e.g. \\n, \\r) so they are valid inside a [...] class.
    """
    return c.encode("unicode_escape").decode() if not c.isprintable() else c


def _build_unsafe_re_class(chars: list[str]) -> str:
    """Build a regex negated character class from a list of unsafe characters."""
    escaped = "".join(_to_regex_char(c) for c in chars)
    return f"[^{escaped}]"


_UNSAFE_RE_CLASS = _build_unsafe_re_class(settings.unsafe_chars)


def glob_to_regex(glob_pattern: str, block_unsafe: bool = True) -> re.Pattern:
    """
    Convert a simple glob pattern containing '*' into a compiled regular expression.

    When block_unsafe=True (the default, used for allow checks), the wildcard '*'
    is restricted to match any character EXCEPT those in settings.unsafe_chars,
    preventing command injection through wildcard expansion.

    When block_unsafe=False (used for deny checks), the wildcard matches any
    character — a deny pattern should be as broad as possible to catch more.

    It also intelligently handles spaces preceding asterisks (e.g., 'show version *'
    will match 'show version' with or without arguments).
    """
    wildcard = _UNSAFE_RE_CLASS if block_unsafe else "."
    escaped = re.escape(glob_pattern.strip())
    escaped = escaped.replace(r"\ \*", rf"(?:\s+{wildcard}*)?")
    escaped = escaped.replace(r"\*", rf"{wildcard}*")

    return re.compile("^" + escaped + "$", re.IGNORECASE)


def deny_check(command: str, denied_commands: list[str]) -> bool:
    """Return True if the command matches any entry in denied_commands.

    Every entry is evaluated via glob_to_regex — the same logic as the allow
    check. A plain string (e.g. 'reload') matches only that exact command.
    A glob (e.g. 'reload *') matches any command starting with 'reload'.
    Denied always takes precedence over allowed.
    """
    for denied in denied_commands:
        if glob_to_regex(denied.strip(), block_unsafe=False).match(command):
            return True
    return False


def load_commands() -> dict[str, Any]:
    """
    Load the command whitelist/blacklist from the command_file defined in global config.
    """
    file_path = Path(settings.command_file).expanduser()
    if file_path.is_file():
        return load_yaml_file(str(file_path))
    return {}


def validate_command(command: str) -> bool:
    """
    Validate that the requested command is safe to execute.

    Rules:
    1. Command must NOT contain any string in 'denied_commands' (supports glob patterns).
    2. Base command (before any pipe) must match a glob/exact string in 'allowed_commands'.
    3. If a pipe is present, 'allow_pipe' must be True, and the pipe modifier
       must be a safe operational filter (e.g. include, exclude, section, begin, count).
    4. Must NOT contain any unsafe characters as defined in settings.unsafe_chars.
    """
    commands = load_commands()

    allowed_commands = commands.get("allowed_commands", DEFAULT_ALLOWED_COMMANDS)
    denied_commands = commands.get("denied_commands", DEFAULT_DENIED_COMMANDS)

    # Reject any command containing an unsafe character.
    if any(char in command for char in settings.unsafe_chars):
        return False

    # Test command against the denied_commands list.
    if deny_check(command, denied_commands):
        return False

    # Extract base command and potential pipe segment
    parts = command.split("|", 1)
    base_command = parts[0].strip()

    # Pipe Check: Validate if a pipe exists
    if len(parts) > 1:
        if not settings.allow_pipe:
            return False

        pipe_modifier = parts[1].strip().lower()
        # Multiple pipes not allowed.
        if "|" in pipe_modifier:
            return False

        if pipe_modifier:
            modifier_keyword = pipe_modifier.split()[0]
            if modifier_keyword not in settings.pipe_modifiers:
                return False
        else:
            return False

    # Test command against the allowed_commands list.
    for allowed in allowed_commands:
        if "*" in allowed:
            pattern = glob_to_regex(allowed)
            if pattern.match(base_command):
                return True
        elif base_command.lower() == allowed.strip().lower():
            return True

    # If it matches no allowed prefix, deny it
    return False

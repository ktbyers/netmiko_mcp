"""
Security validation and command verification layer for the Netmiko MCP server.

Rules:
1. Default Deny: Nothing is allowed unless it is added the whitelist (allowed_commands).
   The whitelist is empty be default.
2. The blacklist (denied_commands) has precedence over the whitelist so if both
   blacklist and whitelist match a given command, then the command is denied.
3. Pipes are denied by default. [THIS WILL BE EXPANDED TO ENCOMPASS ADDITIONAL
   WAYS OF DOING MULTIPLE COMMANDS: FIX].
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


def glob_to_regex(glob_pattern: str) -> re.Pattern:
    """
    Convert a simple glob pattern containing '*' into a compiled regular expression.
    To prevent command injection, the wildcard '*' is compiled to match any character
    EXCEPT those defined in settings.unsafe_chars (newlines, semicolons, ampersands by default).

    It also intelligently handles spaces preceding asterisks (e.g., 'show version *'
    will match 'show version' with or without arguments).
    """
    escaped = re.escape(glob_pattern.strip())
    # Match escaped space followed by escaped asterisk '\ \*'
    # and convert to an optional group of whitespace and safe characters
    escaped = escaped.replace(r"\ \*", rf"(?:\s+{_UNSAFE_RE_CLASS}*)?")
    # Convert any remaining solo asterisks to 0 or more safe characters
    escaped = escaped.replace(r"\*", rf"{_UNSAFE_RE_CLASS}*")

    return re.compile("^" + escaped + "$", re.IGNORECASE)


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
    """
    commands = load_commands()

    allowed_commands = commands.get("allowed_commands", DEFAULT_ALLOWED_COMMANDS)
    denied_commands = commands.get("denied_commands", DEFAULT_DENIED_COMMANDS)

    # Strictly reject command separator characters in the raw input
    # before any whitespace normalization or splitting occurs.
    if any(char in command for char in settings.unsafe_chars):
        return False

    # Normalize whitespace
    command = " ".join(command.split())

    # 1. Deny Check: If it contains any forbidden substring/glob pattern, reject immediately
    for denied in denied_commands:
        denied_str = denied.strip()
        if "*" in denied_str:
            pattern = glob_to_regex(denied_str)
            if pattern.match(command):
                return False
        else:
            if denied_str in command:
                return False

    # Extract base command and potential pipe segment
    parts = command.split("|", 1)
    base_command = parts[0].strip()

    # 2. Pipe Check: Validate if a pipe exists
    if len(parts) > 1:
        if not settings.allow_pipe:
            return False

        # Ensure the pipe modifier is a safe, standard filter.
        # We explicitly block dangerous redirects, file manipulations, or shell escapes
        # (e.g., redirect, append, tee, email, awk, sed, vsh).
        pipe_modifier = parts[1].strip().lower()
        safe_modifiers = (
            # Standard IOS/IOS-XE
            "include",
            "exclude",
            "section",
            "begin",
            "count",
            "i",
            "e",
            "s",
            "b",
            "c",
            # Additional NX-OS safe operational filters
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
        )

        # Check if the first word after the pipe is in our safe list
        modifier_keyword = pipe_modifier.split()[0] if pipe_modifier else ""
        if modifier_keyword not in safe_modifiers:
            return False

    # 3. Allow Check: The base command must match an allowed command pattern
    for allowed in allowed_commands:
        pattern = glob_to_regex(allowed)
        if pattern.match(base_command):
            return True

    # If it matches no allowed prefix, deny it
    return False

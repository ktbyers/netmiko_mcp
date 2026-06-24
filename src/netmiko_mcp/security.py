"""
Security validation and command verification layer for the Netmiko MCP server.

Rules:
1. Default Deny: Nothing is allowed unless it is added to the whitelist (allowed_commands).
   The whitelist is empty by default.
2. The blacklist (denied_commands) has precedence over the whitelist so if both
   blacklist and whitelist match a given command, the command is denied.
3. Pipes are denied by default. Characters not in allowed_command_chars are rejected
   before any other validation.
4. Every attempted and executed command is logged for audit and compliance via the
   audit module. validate_command() returns a ValidationResult carrying both the
   boolean decision and a reason constant so the caller can emit a structured audit
   record with the specific rejection cause (unsafe char, deny match, pipe violation,
   no allow match, etc.).
5. Configuration changes are disallowed by default, both at the Netmiko-level
   (no send_config_set) and at the command-validation level.
6. Globbing is supported ("show *") in both the whitelist and the blacklist.
   Glob patterns are converted to regular expressions internally.

Questions:
1. How to handle the command abbreviation issue?
2. Should we support explicit regular expressions in allowed/denied list?
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from netmiko.utilities import load_yaml_file

from netmiko_mcp.audit import (
    REASON_ALLOWED,
    REASON_DENY_MATCH,
    REASON_INVALID_PIPE_MODIFIER,
    REASON_MULTIPLE_PIPES,
    REASON_NO_ALLOW_MATCH,
    REASON_PIPE_NOT_ALLOWED,
    REASON_UNSAFE_CHAR,
)
from netmiko_mcp.config import settings

# Default fallback if no custom configuration is provided.
# We default to strictly denying everything. Users should provide a YAML
# configuration file to allow commands.
DEFAULT_ALLOWED_COMMANDS: list[str] = []
DEFAULT_DENIED_COMMANDS: list[str] = []


@dataclass
class ValidationResult:
    """The result of a validate_command call.

    allowed indicates whether the command should be permitted. reason is one
    of the REASON_* constants from the audit module and describes why the
    command was allowed or denied. The reason is intended to be recorded
    verbatim in the audit log.
    """

    allowed: bool
    reason: str


def glob_to_regex(glob_pattern: str) -> re.Pattern[str]:
    """
    Convert a simple glob pattern containing '*' into a compiled regular expression.

    The wildcard '*' matches any character. Commands are validated against
    allowed_command_chars before reaching this function, so no additional
    wildcard restriction is needed here.

    A trailing ' *' (space then asterisk) is handled specially so that a pattern
    like 'show version *' matches both 'show version' and 'show version detail'.
    """
    escaped = re.escape(glob_pattern.strip())
    escaped = escaped.replace(r"\ \*", r"(?:\s+.*)?")
    escaped = escaped.replace(r"\*", r".*")

    return re.compile("^" + escaped + "$", re.IGNORECASE)


def deny_check(command: str, denied_commands: list[str]) -> bool:
    """Return True if the command matches any entry in denied_commands.

    Every entry is evaluated via glob_to_regex — the same logic as the allow
    check. A plain string (e.g. 'reload') matches only that exact command.
    A glob (e.g. 'reload *') matches any command starting with 'reload'.
    Denied always takes precedence over allowed.
    """
    for denied in denied_commands:
        if glob_to_regex(denied.strip()).match(command):
            return True
    return False


@lru_cache(maxsize=1)
def load_commands() -> dict[str, Any]:
    """
    Load the command whitelist/blacklist from the command_file defined in global config.
    Result is cached after the first call. A server restart is required to pick up
    changes to commands.yml.
    """
    file_path = Path(settings.command_file).expanduser()
    if file_path.is_file():
        return load_yaml_file(str(file_path))
    return {}


def validate_command(command: str) -> ValidationResult:
    """
    Validate that the requested command is safe to execute.

    Returns a ValidationResult with allowed=True and reason=REASON_ALLOWED if the
    command passes all checks, or allowed=False with a specific reason constant
    indicating why it was rejected. The reason is intended to be recorded in the
    audit log by the caller.

    Rules applied in order:
    - Command must NOT contain any character in settings.unsafe_chars.
    - Command must NOT match any entry in denied_commands (supports glob patterns).
    - If a pipe is present, allow_pipe must be True, and the modifier must be in
      the configured pipe_modifiers list. Multiple pipes are always rejected.
    - Base command (before any pipe) must match an entry in allowed_commands.
    """
    commands = load_commands()

    allowed_commands = commands.get("allowed_commands", DEFAULT_ALLOWED_COMMANDS)
    denied_commands = commands.get("denied_commands", DEFAULT_DENIED_COMMANDS)

    # Reject any command containing an unsafe character.
    if any(char in command for char in settings.unsafe_chars):
        return ValidationResult(allowed=False, reason=REASON_UNSAFE_CHAR)

    # Test command against the denied_commands list.
    if deny_check(command, denied_commands):
        return ValidationResult(allowed=False, reason=REASON_DENY_MATCH)

    # Extract base command and potential pipe segment.
    parts = command.split("|", 1)
    base_command = parts[0].strip()

    # Pipe check: validate if a pipe exists.
    if len(parts) > 1:
        if not settings.allow_pipe:
            return ValidationResult(allowed=False, reason=REASON_PIPE_NOT_ALLOWED)

        pipe_modifier = parts[1].strip().lower()

        # Multiple pipes are never allowed.
        if "|" in pipe_modifier:
            return ValidationResult(allowed=False, reason=REASON_MULTIPLE_PIPES)

        if pipe_modifier:
            modifier_keyword = pipe_modifier.split()[0]
            if modifier_keyword not in settings.pipe_modifiers:
                return ValidationResult(allowed=False, reason=REASON_INVALID_PIPE_MODIFIER)
        else:
            return ValidationResult(allowed=False, reason=REASON_INVALID_PIPE_MODIFIER)

    # Test command against the allowed_commands list.
    for allowed in allowed_commands:
        if "*" in allowed:
            pattern = glob_to_regex(allowed)
            if pattern.match(base_command):
                return ValidationResult(allowed=True, reason=REASON_ALLOWED)
        elif base_command.lower() == allowed.strip().lower():
            return ValidationResult(allowed=True, reason=REASON_ALLOWED)

    # If it matches no allowed entry, deny it.
    return ValidationResult(allowed=False, reason=REASON_NO_ALLOW_MATCH)

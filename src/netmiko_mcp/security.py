"""
Security validation and command verification layer for the Netmiko MCP server.

Security Principles:
1. Default Deny: By default, no commands are permitted. Access must be explicitly
   granted via configuration.
2. Multi-Command Prevention: Command chaining, semi-colons, and unapproved pipes
   are strictly disallowed by default to prevent command injection.
3. Audit Logging: Every attempted and executed command must be logged for audit
   and compliance (TODO).
4. Operational-Only: Configuration changes are disallowed by default, both at the
   Netmiko connection level and the command-validation level.
5. Override Capability: While ultimate control rests with the administrator (who
   can allow any command via custom configuration), the system must make it difficult
   to inadvertently execute destructive actions.
"""

from pathlib import Path
from typing import Any

from netmiko_mcp.config import settings
from netmiko.utilities import load_yaml_file

# Default fallback if no custom configuration is provided
# We default to strictly denying everything. Users MUST provide a YAML configuration
# file to allow commands.
DEFAULT_ALLOWED_COMMANDS: list[str] = []
DEFAULT_DENIED_COMMANDS = ["run", "commit", "clear", "debug"]


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
    1. Command must NOT contain any string in 'denied_commands'.
    2. Base command (before any pipe) must EXACTLY match a string in 'allowed_commands'.
    3. If a pipe is present, 'allow_pipe' must be True, and the pipe modifier
       must be a safe operational filter (e.g. include, exclude, section, begin, count).
    """
    commands = load_commands()

    allowed_commands = commands.get("allowed_commands", DEFAULT_ALLOWED_COMMANDS)
    denied_commands = commands.get("denied_commands", DEFAULT_DENIED_COMMANDS)

    # Deny Check: If it contains any forbidden substring, reject immediately
    for denied in denied_commands:
        if denied in command:
            return False

    # Check for pipe character
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

    # 3. Allow Check: The base command must EXACTLY match an allowed command
    for allowed in allowed_commands:
        if base_command == allowed.strip():
            return True

    # If it matches no allowed prefix, deny it
    return False

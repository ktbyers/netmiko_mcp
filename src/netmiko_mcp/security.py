import os
from typing import Any

from netmiko_mcp.config import settings
from netmiko.utilities import load_yaml_file

# Default fallback if no custom configuration is provided
# We default to strictly denying everything. Users MUST provide a YAML configuration
# file to allow commands.
DEFAULT_ALLOWED_COMMANDS: list[str] = []
DEFAULT_DENIED_COMMANDS = ["|", "run", "commit", "clear", "debug"]


def load_security_config() -> dict[str, Any]:
    """
    Load the command whitelist/blacklist from the file defined in global config.
    """
    config_path = os.path.expanduser(settings.command_file)
    if os.path.isfile(config_path):
        return load_yaml_file(config_path)  # type: ignore
    return {}


def validate_command(command: str) -> bool:
    """
    Validate that the requested command is safe to execute.

    Rules:
    1. Command must not use abbreviations (must start with canonical words).
    2. Command must start with a string in 'allowed_commands'.
    3. Command must NOT contain any string in 'denied_commands'.
    """
    config = load_security_config()

    allowed_commands = config.get("allowed_commands", DEFAULT_ALLOWED_COMMANDS)
    denied_commands = config.get("denied_commands", DEFAULT_DENIED_COMMANDS)

    # 1. Deny Check: If it contains any forbidden substring, reject immediately
    for denied in denied_commands:
        if denied in command:
            return False

    # 2. Allow Check: It must EXACTLY match an allowed command
    for allowed in allowed_commands:
        if command.strip() == allowed.strip():
            return True

    # If it matches no allowed prefix, deny it
    return False

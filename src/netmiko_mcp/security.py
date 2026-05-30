import os
from typing import Any

from netmiko.utilities import load_yaml_file

# Default fallback if no custom configuration is provided
DEFAULT_ALLOWED_PREFIXES = ["show ", "ping ", "traceroute ", "dir "]
DEFAULT_DENIED_SUBSTRINGS = ["|", "run", "commit", "clear", "debug"]


def load_security_config() -> dict[str, Any]:
    """
    Load the command whitelist/blacklist from a YAML file.
    Uses NETMIKO_MCP_SECURITY_CFG if set, otherwise defaults to None.
    """
    config_path = os.environ.get("NETMIKO_MCP_SECURITY_CFG")
    if config_path and os.path.isfile(config_path):
        return load_yaml_file(config_path)  # type: ignore
    return {}


def validate_command(command: str) -> bool:
    """
    Validate that the requested command is safe to execute.

    Rules:
    1. Command must not use abbreviations (must start with canonical words).
    2. Command must start with a string in 'allowed_prefixes'.
    3. Command must NOT contain any string in 'denied_substrings'.
    """
    config = load_security_config()

    allowed_prefixes = config.get("allowed_prefixes", DEFAULT_ALLOWED_PREFIXES)
    denied_substrings = config.get("denied_substrings", DEFAULT_DENIED_SUBSTRINGS)

    # 1. Deny Check: If it contains any forbidden substring, reject immediately
    for denied in denied_substrings:
        if denied in command:
            return False

    # 2. Allow Check: It must start exactly with an allowed prefix
    # (e.g. "show " prevents "sh " abbreviation)
    for allowed in allowed_prefixes:
        if command.startswith(allowed):
            return True

    # If it matches no allowed prefix, deny it
    return False

---
name: netmiko-tools-yml
description: Workflows and references for using the Netmiko CLI tools .netmiko.yml format for device inventory, credential management, and encryption.
---

# Netmiko Tools YAML (.netmiko.yml)

The `.netmiko.yml` file is the standard inventory and credential storage mechanism for Netmiko's built-in CLI tools (`netmiko-show`, `netmiko-cfg`, `netmiko-grep`). For the Netmiko MCP server, this format is used to securely load device details without forcing the LLM to handle plaintext passwords.

## File Format

The YAML file contains a `__meta__` block (optional, used for configuring encryption) and standard device blocks. The device blocks represent dictionaries that can be directly unpacked into Netmiko's `ConnectHandler`.

```yaml
__meta__:
  encryption: true
  encryption_type: fernet  # Options: fernet, aes128

cisco_router_1:
  device_type: cisco_ios
  host: 192.168.1.1
  username: admin
  password: >
    __encrypt__gAAAAABn... # Long encrypted string
```

## Environment Variables

- `NETMIKO_TOOLS_CFG`: Overrides the path to the configuration file (default behavior searches the current directory `./.netmiko.yml` then the home directory `~/.netmiko.yml`).
- `NETMIKO_TOOLS_KEY`: The encryption key required to decrypt any values prefixed with `__encrypt__`.

## Python API for Loading (Important for MCP)

Netmiko provides utilities to discover, parse, and decrypt this file automatically. When building tools that need to resolve device names to connection parameters, use these built-in functions:

```python
from netmiko.utilities import find_cfg_file, load_yaml_file, obtain_all_devices

# 1. Find the .netmiko.yml file (respects NETMIKO_TOOLS_CFG)
try:
    cfg_file = find_cfg_file()
except ValueError as e:
    # Handle case where file is not found
    pass

# 2. Parse the YAML file into a dictionary
parsed_yaml = load_yaml_file(cfg_file)

# 3. Extract devices and decrypt credentials
# This automatically looks for the NETMIKO_TOOLS_KEY and decrypts fields starting with __encrypt__
# Returns a dict: {"cisco_router_1": {"device_type": "cisco_ios", "host": "...", ...}}
devices = obtain_all_devices(parsed_yaml)
```

## Encryption Management (CLI)

To manually encrypt passwords to place into the YAML file, users can leverage Netmiko's provided CLI utilities:
- `netmiko-encrypt --text <password>`: Encrypts a single string using the key in `NETMIKO_TOOLS_KEY`.
- `netmiko-bulk-encrypt --input-file <file>`: Safely encrypts an entire `.netmiko.yml` file in place.
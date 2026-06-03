# Netmiko MCP Server

> **WARNING:** You can make serious, incredibly detrimental mistakes by using this tool. This tool could cause massive outages in your environment. You, and you alone, are solely responsible for using this tool. Don't say I didn't warn you.

## Getting Started

Create a Netmiko MCP Configuration file (see [MCP Configuration](#mcp-configuration)). In this file you should specify the following:

```yaml
---
# Netmiko Tools Inventory Format (only inventory format currently supported)
inventory_type: netmiko_tools

# Netmiko Tools Inventory File Location
inventory_file: "/path/to/netmiko_inventory.yml"

# Define allowed_commands and denied_commands (see LINK)
command_file: "/path/to/commands.yml"
```

Set the **`NETMIKO_MCP_CONFIG`** environment variable and point this at the Netmiko MCP Configuration file that you just created.

The Netmiko CLI tool inventory format is detailed [HERE](https://pynet.twb-tech.com/blog/netmiko-grep-command-line-utility.html#creating-the-inventory). Additionally, there is AI [skill file](https://github.com/ktbyers/netmiko_mcp/blob/main/skills/netmiko-tools-yml/SKILL.md) available.

In your commands.yml, you must specify which commands are allowed (see LINK):

```yaml
---                                                                                                                              
# Netmiko MCP Command Whitelist

# By default, no commands are allowed.

allowed_commands:
  - "show version"

# Explicitly denied commands/substrings (these override allowed_commands)
denied_commands: []
```

The above commands.yml file should allow only "show version" and no other commands to be executed.

## MCP Configuration

The Netmiko MCP Server has a YAML-based configuration file. requires configuration to understand where your inventory lives and what commands are permitted.

### 1. Global Configuration File
By default, the server looks for a configuration file at **`~/.netmiko-mcp.yml`** (in your home directory).
You can override this location by setting the **`NETMIKO_MCP_CONFIG`** environment variable.

Create a `~/.netmiko-mcp.yml` file with the following minimum required settings:

```yaml
---
# Optional: explicitly define inventory type (Defaults to netmiko_tools)
inventory_type: "netmiko_tools"
# Optional: explicitly point to your .netmiko.yml inventory (If omitted, defaults to standard Netmiko search paths: NETMIKO_TOOLS_CFG env var -> ./.netmiko.yml -> ~/.netmiko.yml)
# inventory_file: "~/.netmiko.yml"
# Optional: Explicitly point to your commands.yml whitelist (Defaults to ~/commands.yml)
command_file: "~/commands.yml"
# Optional: Allow safe piping logic (e.g. | include). Defaults to false.
allow_pipe: true
```

*Note: Environment variables prefixed with `NETMIKO_MCP_` (e.g., `NETMIKO_MCP_ALLOW_PIPE=false`) will always override the values inside the YAML file.*

### 2. Device Inventory and Credentials
Because `inventory_type` is set to `netmiko_tools`, the server natively uses the standard Netmiko Tools YAML inventory format.
- Create your `~/.netmiko.yml` file containing your devices and encrypted credentials.
- Ensure you have the `NETMIKO_TOOLS_KEY` environment variable exported in the shell where your MCP client runs so the server can decrypt the credentials securely.

### 3. Security Whitelist
Create a `~/commands.yml` file to restrict what the LLM is allowed to do. By default, the server strictly denies *all* commands unless they are explicitly whitelisted.

```yaml
---
# Exact matches or globs (*) permitted
allowed_commands:
  - "show version *"
  - "show ip interface brief"

# Commands that are instantly blocked regardless of whitelist
denied_commands:
  - "configure terminal"
  - "reload"
```

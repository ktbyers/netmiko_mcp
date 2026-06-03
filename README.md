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

# Explicitly denied commands (these override allowed_commands).
# Uses the same exact/glob matching as allowed_commands.
denied_commands: []
```

The above commands.yml file should allow only "show version" and no other commands to be executed.

## MCP Configuration

The Netmiko MCP Server has a YAML-based configuration file that controls where your inventory lives, what commands are permitted, and how pipe operators behave.

### 1. Global Configuration File
By default, the server looks for a configuration file at **`~/.netmiko-mcp.yml`** (in your home directory).
You can override this location by setting the **`NETMIKO_MCP_CONFIG`** environment variable.

Create a `~/.netmiko-mcp.yml` file with the following settings:

```yaml
---
# Optional: explicitly define inventory type (Defaults to netmiko_tools)
inventory_type: "netmiko_tools"
# Optional: explicitly point to your .netmiko.yml inventory (If omitted, defaults to standard Netmiko search paths: NETMIKO_TOOLS_CFG env var -> ./.netmiko.yml -> ~/.netmiko.yml)
# inventory_file: "~/.netmiko.yml"
# Optional: Explicitly point to your commands.yml whitelist (Defaults to ~/commands.yml)
command_file: "~/commands.yml"
# Optional: Allow pipe operators (e.g. | include, | exclude). Defaults to false.
allow_pipe: true
# Optional: Characters unconditionally blocked in any command before validation.
# Defaults to the four characters below. Override if your platform requires different separators.
unsafe_chars: [";", "\n", "\r", "&"]
# Optional: Pipe operators permitted when allow_pipe is true.
# Defaults to the five IOS/IOS-XE operators below. Add NX-OS or others as needed.
pipe_modifiers: ["include", "exclude", "section", "begin", "count"]
```

*Note: Environment variables prefixed with `NETMIKO_MCP_` (e.g., `NETMIKO_MCP_ALLOW_PIPE=false`) will always override the values inside the YAML file.*

### 2. Device Inventory and Credentials
Because `inventory_type` is set to `netmiko_tools`, the server natively uses the standard Netmiko Tools YAML inventory format.
- Create your `~/.netmiko.yml` file containing your devices and encrypted credentials.
- Ensure you have the `NETMIKO_TOOLS_KEY` environment variable exported in the shell where your MCP client runs so the server can decrypt the credentials securely.

### 3. Security Whitelist (`~/commands.yml`)
Create a `~/commands.yml` file to restrict what the LLM is allowed to do. By default, the server strictly denies *all* commands unless they are explicitly whitelisted.

Both `allowed_commands` and `denied_commands` use the same matching rules:
- A **plain string** (e.g. `"reload"`) matches only that exact command.
- A **glob** (e.g. `"reload *"`) matches the bare command or any command starting with that prefix followed by arguments.
- `denied_commands` always takes precedence over `allowed_commands`.

```yaml
---
# Exact matches or globs (*) permitted
allowed_commands:
  - "show version *"
  - "show ip interface brief"

# Commands denied regardless of the whitelist.
# "reload" matches only the bare command "reload".
# "configure *" matches "configure terminal", "configure replace", etc.
denied_commands:
  - "configure *"
  - "reload"
```

### 4. Unsafe Characters (`unsafe_chars`)
The `unsafe_chars` setting defines characters that are **unconditionally rejected** in any command string before any whitelist or glob matching takes place. This is the first line of defence against command injection.

Default:
```yaml
unsafe_chars: [";", "\n", "\r", "&"]
```

Override in `~/.netmiko-mcp.yml` or via environment variable (JSON array):
```
NETMIKO_MCP_UNSAFE_CHARS='[";", "\n", "\r", "&", "|"]'
```

> **Note:** Only add to this list — do not remove the defaults unless you fully understand the security implications.

### 5. Pipe Support (`allow_pipe` and `pipe_modifiers`)
By default, pipe operators (`|`) are **disabled**. Set `allow_pipe: true` in `~/.netmiko-mcp.yml` (or `NETMIKO_MCP_ALLOW_PIPE=true`) to enable them.

When enabled, the base command is still validated against `allowed_commands`. The first keyword after the pipe is checked against `pipe_modifiers` — anything not in that list is blocked.

**`pipe_modifiers`** controls which operators are permitted. Default (IOS/IOS-XE):
```yaml
pipe_modifiers: ["include", "exclude", "section", "begin", "count"]
```

Extend for NX-OS or other platforms in `~/.netmiko-mcp.yml`:
```yaml
pipe_modifiers:
  - "include"
  - "exclude"
  - "section"
  - "begin"
  - "count"
  - "grep"
  - "egrep"
  - "json"
  - "json-pretty"
  - "xml"
  - "no-more"
```

Or via environment variable (JSON array):
```
NETMIKO_MCP_PIPE_MODIFIERS='["include", "exclude", "section", "begin", "count", "grep"]'
```

Anything not in `pipe_modifiers` is **always blocked** — there is no separate blocklist.


# Netmiko MCP — Configuration File

The Netmiko MCP server is configured via a central YAML file. This document covers every
supported setting, its default value, and the corresponding environment variable override.


## File Location

By default the server looks for:

```
~/.netmiko-mcp.yml
```

Override the path by setting the `NETMIKO_MCP_CONFIG` environment variable **before** the
server starts. The recommended way to do this is via your MCP client's `env` block rather
than your shell profile, since the server is typically launched by the client process:

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "netmiko-mcp",
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/your/netmiko-mcp.yml",
        "NETMIKO_TOOLS_KEY": "<your-decryption-key>"
      }
    }
  }
}
```


## Settings Reference

All environment variable overrides use the prefix `NETMIKO_MCP_`. Environment variables
always take precedence over the YAML file, which always takes precedence over built-in
defaults.

| Field | Type | Default | Env var override | Description |
|---|---|---|---|---|
| `inventory_type` | `string` | `"netmiko_tools"` | `NETMIKO_MCP_INVENTORY_TYPE` | Inventory backend. Only `netmiko_tools` is currently supported. |
| `inventory_file` | `string \| null` | `null` | `NETMIKO_MCP_INVENTORY_FILE` | Explicit path to your Netmiko inventory YAML. If omitted, Netmiko's native search order applies (see below). |
| `command_file` | `string` | `"~/commands.yml"` | `NETMIKO_MCP_COMMAND_FILE` | Path to your [commands.yml](commands.md) security whitelist. |
| `allow_pipe` | `bool` | `false` | `NETMIKO_MCP_ALLOW_PIPE` | Enable pipe operators (`\|`) in commands. See [commands.md — Pipe Support](commands.md#pipe-support). |
| `unsafe_chars` | `list[str]` | `[";", "\n", "\r", "&"]` | `NETMIKO_MCP_UNSAFE_CHARS` | Characters unconditionally rejected before any validation. See [commands.md — Unsafe Characters](commands.md#unsafe-characters). |
| `pipe_modifiers` | `list[str]` | `["include", "exclude", "section", "begin", "count"]` | `NETMIKO_MCP_PIPE_MODIFIERS` | Permitted keywords after a pipe operator. See [commands.md — Pipe Support](commands.md#pipe-support). |


## Setting Details

### `inventory_type`

Only `netmiko_tools` is currently supported. The value must be an exact match.

```yaml
inventory_type: "netmiko_tools"
```

### `inventory_file`

Points the server at your Netmiko Tools inventory YAML (the file containing your device
definitions and encrypted credentials). If omitted, Netmiko's native search order is used:

1. `NETMIKO_TOOLS_CFG` environment variable
2. `./.netmiko.yml` (current working directory)
3. `~/.netmiko.yml` (home directory)

The inventory format is documented [here](https://pynet.twb-tech.com/blog/netmiko-grep-command-line-utility.html#creating-the-inventory).
There is also a dedicated [skill file](https://github.com/ktbyers/netmiko_mcp/blob/main/skills/netmiko-tools-yml/SKILL.md) for AI-assisted inventory creation.

```yaml
inventory_file: "~/.netmiko.yml"
```

The server requires `NETMIKO_TOOLS_KEY` to be set in the environment so it can decrypt
`__encrypt__` fields in the inventory. Set it in your MCP client's `env` block.

### `command_file`

Path to your `commands.yml` security whitelist. Defaults to `~/commands.yml`. The full
format and behavior are documented in [commands.md](commands.md).

```yaml
command_file: "~/commands.yml"
```

### `allow_pipe`

Controls whether pipe operators (`|`) are permitted in commands. `false` by default. When
`true`, only keywords listed in `pipe_modifiers` are accepted after the pipe. Full details
in [commands.md — Pipe Support](commands.md#pipe-support).

```yaml
allow_pipe: false
```

### `unsafe_chars`

A list of characters that are unconditionally rejected in any command string before any
whitelist or glob matching takes place. These characters are the first line of defence
against command injection. Full details in [commands.md — Unsafe Characters](commands.md#unsafe-characters).

```yaml
unsafe_chars: [";", "\n", "\r", "&"]
```

> **Note:** Only add to this list — do not remove the defaults unless you fully understand
> the security implications.

Environment variable override accepts a JSON array:
```
NETMIKO_MCP_UNSAFE_CHARS='[";", "\n", "\r", "&", "|"]'
```

### `pipe_modifiers`

The list of pipe operator keywords that are permitted when `allow_pipe` is `true`. Defaults
to the five standard IOS/IOS-XE operators. Extend this list for NX-OS or other platforms.
Full details in [commands.md — Pipe Support](commands.md#pipe-support).

```yaml
pipe_modifiers: ["include", "exclude", "section", "begin", "count"]
```

Environment variable override accepts a JSON array:
```
NETMIKO_MCP_PIPE_MODIFIERS='["include", "exclude", "section", "begin", "count", "grep"]'
```


## Complete Example

```yaml
---
# ~/.netmiko-mcp.yml

# Inventory
inventory_type: "netmiko_tools"
inventory_file: "~/.netmiko.yml"

# Security whitelist
command_file: "~/commands.yml"

# Pipe support (disabled by default)
allow_pipe: true
pipe_modifiers:
  - "include"
  - "exclude"
  - "section"
  - "begin"
  - "count"

# Injection protection (defaults shown — rarely need changing)
unsafe_chars: [";", "\n", "\r", "&"]
```


## Settings Priority

From highest to lowest:

1. **Environment variables** (`NETMIKO_MCP_*`) — always win
2. **`~/.netmiko-mcp.yml`** (or the path in `NETMIKO_MCP_CONFIG`)
3. **Built-in defaults** (shown in the table above)

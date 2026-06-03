---
name: netmiko-mcp
description: Workflows and configuration references for the Netmiko MCP server, including environment variables, global config (netmiko-mcp.yml), and security commands (commands.yml).
---

# Netmiko MCP Server Architecture & Configuration

The Netmiko MCP server exposes network devices to Model Context Protocol clients (like Claude Code) via a highly secure, restricted gateway.

## Global Configuration (`~/.netmiko-mcp.yml`)

The server is configured via a central YAML file.
- **Default Location:** `~/.netmiko-mcp.yml`
- **Override:** Set the `NETMIKO_MCP_CONFIG` environment variable to a custom path.
- **Precedence:** Environment variables starting with `NETMIKO_MCP_` (e.g., `NETMIKO_MCP_ALLOW_PIPE=false`) always override keys defined in the YAML file.

### Supported Fields
```yaml
---
inventory_type: "netmiko_tools"          # Optional (Defaults to netmiko_tools. Must be exact match)
# inventory_file: "~/.netmiko.yml"       # Optional. If omitted, uses native Netmiko search paths (NETMIKO_TOOLS_CFG env var -> ./.netmiko.yml -> ~/.netmiko.yml)
command_file: "~/commands.yml"           # Optional (Defaults to ~/commands.yml. Path to security rules)
allow_pipe: true                         # Optional (Defaults to false. Enables safe read-only pipe operators — see Pipe Support below)
unsafe_chars: [";", "\n", "\r", "&"]    # Optional (Defaults to these four. Characters unconditionally blocked before any validation — see Unsafe Characters below)
```

## Security Whitelist (`~/commands.yml`)

Security relies on an explicit whitelist mapped via the `command_file` property. By default, **all commands are denied**.

- **allowed_commands**: Exact strings or globs (`*`) the user is allowed to send. (e.g., `show version *`). The `*` wildcard safely blocks command injection operators like `;`, `\n`, or `&`.
- **denied_commands**: Substrings or globs that instantly block execution, superseding the whitelist.

```yaml
---
allowed_commands:
  - "show version *"
  - "show ip int brief"
denied_commands:
  - "configure *"
  - "reload"
```

## Unsafe Characters (`unsafe_chars`)

`unsafe_chars` defines the set of characters that are **unconditionally rejected** in any command string before whitelist matching or glob evaluation. It is the first line of defence against command injection.

**Default:** `[";", "\n", "\r", "&"]`

Override in `~/.netmiko-mcp.yml`:
```yaml
unsafe_chars: [";", "\n", "\r", "&", "|"]
```

Or via environment variable (JSON array):
```
NETMIKO_MCP_UNSAFE_CHARS='[";", "\n", "\r", "&", "|"]'
```

> Only add to this list — do not remove the defaults unless you fully understand the security implications.

## Pipe Support (`allow_pipe`)

`allow_pipe` is `false` by default. Set it to `true` in `~/.netmiko-mcp.yml` or via `NETMIKO_MCP_ALLOW_PIPE=true` to enable pipe operators.

When enabled, the base command is still validated against `allowed_commands`. Only the pipe modifier keyword is checked — it must be on the safe list below. Anything not on the list is blocked.

### Safe pipe operators

| Platform | Operators |
|---|---|
| IOS / IOS-XE | `include`, `exclude`, `section`, `begin`, `count` (shortcuts: `i`, `e`, `s`, `b`, `c`) |
| NX-OS (text) | `grep`, `egrep`, `head`, `last`, `less`, `no-more`, `sort`, `uniq`, `wc`, `nz`, `end` |
| NX-OS (structured) | `json`, `json-pretty`, `xml`, `xmlin`, `xmlout`, `human` |

### Always blocked (even with `allow_pipe: true`)
`redirect`, `append`, `tee`, `awk`, `sed`, `cut`, `tr`, `vsh`, `email`, `diff`, and any operator not in the safe list.

### Example
```yaml
# ~/.netmiko-mcp.yml
allow_pipe: true
command_file: "~/commands.yml"
```
```
# These work when allow_pipe: true and "show version *" is in allowed_commands
show version | include IOS
show version | exclude uptime
show version | json

# These are always blocked
show version | redirect tftp://1.1.1.1/out.txt
show version | awk '{print $1}'
```

## The Inventory (`~/.netmiko.yml`)

Because the server uses the `netmiko_tools` inventory type, it natively leverages Netmiko's encrypted YAML format.
- Do not expose plaintext credentials in the `list_devices` MCP payload.
- The server requires the `NETMIKO_TOOLS_KEY` environment variable to be exported in the executing shell to perform PBKDF2HMAC decryption of `__encrypt__` fields.

See the `netmiko-tools-yml` skill for a deeper dive into inventory generation and encryption mechanics.

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
allow_pipe: true                         # Optional (Defaults to false. Enables safe regex/formatting pipes)
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

## The Inventory (`~/.netmiko.yml`)

Because the server uses the `netmiko_tools` inventory type, it natively leverages Netmiko's encrypted YAML format.
- Do not expose plaintext credentials in the `list_devices` MCP payload.
- The server requires the `NETMIKO_TOOLS_KEY` environment variable to be exported in the executing shell to perform PBKDF2HMAC decryption of `__encrypt__` fields.

See the `netmiko-tools-yml` skill for a deeper dive into inventory generation and encryption mechanics.

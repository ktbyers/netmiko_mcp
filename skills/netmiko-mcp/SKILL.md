---
name: netmiko-mcp
description: Workflows and configuration references for the Netmiko MCP server, including environment variables, global config (netmiko-mcp.yml), security commands (commands.yml), and running the server over Streamable HTTP transport with bearer token authentication.
---

# Netmiko MCP Server — Configuration Reference

The Netmiko MCP server exposes network devices to Model Context Protocol clients (like Claude Code) via a highly secure, restricted gateway.

## Global Configuration (`~/.netmiko-mcp.yml`)

The server is configured via a central YAML file.
- **Default Location:** `~/.netmiko-mcp.yml`
- **Override:** Set the `NETMIKO_MCP_CONFIG` environment variable to a custom path.
- **Precedence:** Environment variables starting with `NETMIKO_MCP_` always override keys defined in the YAML file.

### Supported Fields
```yaml
---
inventory_type: "netmiko_tools"          # default: netmiko_tools (only supported value)
# inventory_file: "~/.netmiko.yml"       # default: null — uses native Netmiko search paths
command_file: "~/commands.yml"           # default: ~/commands.yml
allow_pipe: false                        # default: false
unsafe_chars: [";", "\n", "\r", "&"]    # default: these four
pipe_modifiers: ["include", "exclude", "section", "begin", "count"]  # default: these five
max_workers: 10                          # default: 10 (thread cap for send_show_command_to_group)
save_output_dir: "~/.netmiko_mcp_tmp"   # default: ~/.netmiko_mcp_tmp (save_output=True files)
transport: "stdio"                       # default: stdio (or streamable-http)
http_host: "127.0.0.1"                  # default: 127.0.0.1
http_port: 8000                          # default: 8000
http_path: "/mcp"                        # default: /mcp
http_auth_enabled: true                  # default: true (bearer token is env-only: NETMIKO_MCP_HTTP_BEARER_TOKEN)
audit_log_enabled: true                  # default: true
audit_log_destination: "file"            # default: file (file | syslog | both)
audit_log_file: "~/.netmiko_mcp_audit.log"  # default: ~/.netmiko_mcp_audit.log
# audit_log_syslog_address: "/dev/log"  # default: /dev/log (or host:port for remote UDP)
# audit_log_syslog_facility: "local0"   # default: local0
audit_log_read_transcript: false         # default: false
audit_log_transcript_dir: "~/.netmiko_mcp_transcripts"  # default: ~/.netmiko_mcp_transcripts
```

## Security Whitelist (`~/commands.yml`)

Default: all commands denied. Path set by `command_file`. Both lists use the same matching rules:
- A **plain string** (e.g. `"reload"`) matches only that exact command — anchored at both ends.
- A **glob** (e.g. `"reload *"`) matches the bare command or any command starting with that prefix followed by arguments.
- `denied_commands` always takes precedence over `allowed_commands`.

```yaml
---
allowed_commands:
  - "show version *"
  - "show ip int brief"
denied_commands:
  - "configure *"   # blocks "configure terminal", "configure replace", etc.
  - "reload"        # blocks only the bare "reload" command
```

## Unsafe Characters (`unsafe_chars`)

Characters unconditionally rejected before whitelist matching or glob evaluation. Default: `[";", "\n", "\r", "&"]`. Only add to this list — do not remove the defaults.

Override in `~/.netmiko-mcp.yml`:
```yaml
unsafe_chars: [";", "\n", "\r", "&", "|"]
```

Or via environment variable (JSON array):
```
NETMIKO_MCP_UNSAFE_CHARS='[";", "\n", "\r", "&", "|"]'
```

## Pipe Support (`allow_pipe` and `pipe_modifiers`)

`allow_pipe` is `false` by default. Set it to `true` in `~/.netmiko-mcp.yml` or via `NETMIKO_MCP_ALLOW_PIPE=true` to enable pipe operators.

When enabled, the base command is still validated against `allowed_commands`. The first keyword after the pipe is checked against `pipe_modifiers` — anything not in that list is blocked.

### `pipe_modifiers`

Default (IOS/IOS-XE):
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

### Example
```yaml
# ~/.netmiko-mcp.yml
allow_pipe: true
pipe_modifiers: ["include", "exclude", "section", "begin", "count", "grep", "json"]
command_file: "~/commands.yml"
```
```
# These work when allow_pipe: true and "show version *" is in allowed_commands
show version | include IOS
show version | exclude uptime
show version | grep router      # only if "grep" is in pipe_modifiers

# These are always blocked (not in pipe_modifiers)
show version | awk '{print $1}'
show version | redirect tftp://1.1.1.1/out.txt
```

## MCP Tools

| Tool | Arguments | Description |
|---|---|---|
| `send_show_command` | `device_name`, `command`, `use_textfsm=False` | Connect to a single device and execute a show command. Returns raw text or structured JSON when `use_textfsm=True`. |
| `send_show_command_to_group` | `device_or_group`, `command`, `use_textfsm=False`, `save_output=False` | Execute a show command concurrently across a device group using a thread pool (`max_workers`). When `save_output=True`, writes per-device output files under `save_output_dir` and returns file paths instead of raw output. |
| `list_devices` | `device_or_group="all"` | List devices from the inventory. Credentials are never included in the response. |
| `list_groups` | _(none)_ | List all device group names defined in the inventory. Returns a list of strings. |
| `list_device_outputs` | `device_or_group` | List saved output files for a device, group, or `"all"`. Returns a dict mapping device names to lists of filenames (newest first). |
| `read_device_output` | `device_name`, `filename` | Read a previously saved output file by device name and exact filename (as returned by `list_device_outputs`). |
| `ping` | _(none)_ | Health check. Returns `"pong"`. |

---

## The Inventory (`~/.netmiko.yml`)

- `NETMIKO_TOOLS_KEY` must be set in the environment to decrypt `__encrypt__` fields.
- Credentials are never included in `list_devices` responses.

See the `netmiko-tools-yml` skill for inventory format, encryption walkthrough, and secrets manager integration.

---

## Related Skills

- **`netmiko-tools-yml`** — Device inventory file format (`.netmiko.yml`), Fernet encryption walkthrough, secrets manager integration, Python API for credential loading
- **`mcp-client-config`** — Connecting MCP clients (Claude Code, Claude Desktop, Cursor, Devin Desktop, VS Code, Kiro) to this server; per-client JSON config blocks and gotchas
- **`mcp-http-transport`** — Enabling and deploying the Streamable HTTP transport, HTTP bridge options for web clients (ChatGPT, Perplexity), SSE vs Streamable HTTP comparison

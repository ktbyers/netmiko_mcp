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
allowed_command_chars: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ./:_-,\""  # default
pipe_modifiers: ["include", "exclude", "section", "begin", "count"]  # default: these five
max_workers: 10                          # default: 10 (thread cap for send_show_command_to_group)
save_output_dir: "~/.netmiko_mcp_tmp"   # default: ~/.netmiko_mcp_tmp (all saved output lands here)
save_threshold: 1000                     # default: 1000 (lines; output above this is auto-saved)
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

Default: all commands denied. Path set by `command_file`.

### Matching rules

**Allow list** (`allowed_commands`):
- A **plain string** (e.g. `"show version"`) matches only that exact command — case-insensitive, anchored at both ends. Abbreviations are NOT supported (`"sh ver"` does not match).
- An **inline glob** (e.g. `"show version*"`) matches the bare command and any suffix: `show version`, `show versions`, `show version detail` all match.
- A **space glob** (e.g. `"show version *"`) requires at least one additional word: `show version detail` matches, but `show version` alone does NOT.

**Deny list** (`denied_commands`):
- A **plain string** (e.g. `"reload"`) denies that exact command AND all abbreviated forms of the same word count — `rel`, `relo`, `reloa`, `reload` are all denied. Commands with more or fewer words are NOT covered.
- An **inline glob** (e.g. `"reload*"`) denies the bare command and any suffix, including abbreviated first words.
- A **space glob** (e.g. `"reload *"`) denies commands with at least one additional word, including abbreviated forms. The bare command alone is NOT denied.
- `denied_commands` always takes precedence over `allowed_commands`.

```yaml
---
allowed_commands:
  - "show version*"    # matches bare 'show version' and any arguments
  - "show ip int brief"
denied_commands:
  - "configure*"  # blocks 'configure', 'configure terminal', 'conf t', etc.
  - "reload*"     # blocks 'reload', 'rel', 'reload in 5', 'reload cancel', etc.
```

## Allowed Characters (`allowed_command_chars`)

Allowlist of characters permitted in commands. Any character not in this set is rejected before any deny/allow matching. Default covers `a-z A-Z 0-9` and `<space> . / : _ - , "`.

Whitespace normalization runs before this check: all ASCII whitespace runs (tabs, multiple spaces, etc.) are collapsed to a single space and leading/trailing whitespace is stripped. The normalized form is what is validated and forwarded to the device — capitalization is preserved.

The pipe character `|` must not be added here when `allow_pipe` is `false`. It is added to the effective allowed set automatically when `allow_pipe` is `true`.

Extend in `~/.netmiko-mcp.yml`:
```yaml
allowed_command_chars: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ./:_-,\""
```

Or via environment variable:
```
NETMIKO_MCP_ALLOWED_COMMAND_CHARS='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ./:_-,"'
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
  - "json"
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
| `send_show_command` | `device_name`, `command`, `use_textfsm=False`, `save_output=False` | Connect to a single device and execute a show command. Returns raw text or structured JSON when `use_textfsm=True`. Pass `save_output=True` to always save to disk regardless of output size. Output exceeding `save_threshold` is automatically saved even when `save_output=False`. |
| `send_show_command_to_group` | `device_or_group`, `command`, `use_textfsm=False`, `save_output=False` | Execute a show command concurrently across a device group using a thread pool (`max_workers`). `save_output=True` and auto-save threshold behave identically to `send_show_command`, applied per device. |
| `list_devices` | `device_or_group="all"` | List devices from the inventory. Credentials are never included in the response. |
| `list_groups` | _(none)_ | List all device group names defined in the inventory. Returns a list of strings. |
| `list_device_outputs` | `device_or_group` | List saved output files for a device, group, or `"all"`. Returns a dict mapping device names to lists of filenames (newest first). |
| `read_device_output` | `device_name`, `filename`, `offset=0`, `limit=500` | Read a previously saved output file by device name and exact filename. Returns a paginated slice with a header showing line range and total (`Lines 1-500 of 42000. Call read_device_output with offset=500 to continue.`). Use `offset` and `limit` to page through large files. |
| `ping` | _(none)_ | Health check. Returns `"pong"`. |

## Large Output Handling

Both `send_show_command` and `send_show_command_to_group` handle large output the same way.

**Explicit save** (`save_output=True`): always saves to `save_output_dir` regardless of size. Returns `"Output saved as 'filename.txt'."`. Use when you intend to reference the output multiple times without re-running the command.

**Auto-save** (`save_output=False`, output exceeds `save_threshold`): automatically saves and returns a notification:
```
Output too large to return inline (42,000 lines, exceeds save_threshold of 1,000).
Automatically saved as 'show_ip_bgp_20260622_143201.txt'.
Use read_device_output to retrieve it.
```

**Retrieving saved output**: call `list_device_outputs` to find the filename, then `read_device_output` with `offset`/`limit` to page through the content. The response header on every page shows position and total:
```
Lines 1-500 of 42000. Call read_device_output with offset=500 to continue.
<content...>
```
The filename (not the full server path) is returned in all notifications.

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

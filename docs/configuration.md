# Netmiko MCP — Configuration File

The Netmiko MCP server is configured via a YAML file. This document covers the supported
settings, their default values, and the corresponding environment variables.
<br />
<br />

## File Location

By default the server looks for:

```
~/.netmiko-mcp.yml
```

Override the path by setting the `NETMIKO_MCP_CONFIG` environment variable **before** the
server starts.
<br />
<br />

## Settings Reference

All environment variable overrides use the prefix `NETMIKO_MCP_`. Environment variables
always take precedence over the YAML file, which always takes precedence over built-in
defaults.

### General

| Field | Type | Default | Env var override | Description |
|---|---|---|---|---|
| `inventory_type` | `string` | `"netmiko_tools"` | `NETMIKO_MCP_INVENTORY_TYPE` | Inventory backend. Only `netmiko_tools` is currently supported. |
| `inventory_file` | `string \| null` | `null` | `NETMIKO_MCP_INVENTORY_FILE` | Explicit path to your Netmiko inventory YAML. If omitted, Netmiko's native search order applies (see below). |
| `command_file` | `string` | `"~/commands.yml"` | `NETMIKO_MCP_COMMAND_FILE` | Path to your [commands.yml](commands.md) security whitelist. |
| `allow_pipe` | `bool` | `false` | `NETMIKO_MCP_ALLOW_PIPE` | Enable pipe operators (`\|`) in commands. See [commands.md — Pipe Support](commands.md#pipe-support). |
| `allowed_command_chars` | `string` | `"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ./:_-,"` | `NETMIKO_MCP_ALLOWED_COMMAND_CHARS` | Characters permitted in commands. Any character not in this set is rejected before validation. `\|` is managed via `allow_pipe`. See [commands.md — Allowed Characters](commands.md#allowed-characters). |
| `pipe_modifiers` | `list[str]` | `["include", "exclude", "section", "begin", "count"]` | `NETMIKO_MCP_PIPE_MODIFIERS` | Permitted keywords after a pipe operator. See [commands.md — Pipe Support](commands.md#pipe-support). |
| `max_workers` | `int` | `10` | `NETMIKO_MCP_MAX_WORKERS` | Maximum concurrent threads used by `send_show_command_to_group`. |
| `save_output_dir` | `string` | `"~/.netmiko_mcp_tmp"` | `NETMIKO_MCP_SAVE_OUTPUT_DIR` | Base directory for per-device output files written when `save_output=True` is passed to either `send_show_command` or `send_show_command_to_group`, or when output is automatically saved due to `save_threshold`. Created with mode `0o700`. |
| `save_threshold` | `int` | `1000` | `NETMIKO_MCP_SAVE_THRESHOLD` | Line count above which command output is automatically saved to `save_output_dir` instead of being returned inline. Applies to both `send_show_command` and `send_show_command_to_group` (when `save_output=False`). The LLM receives a notification with the filename and instructions to use `read_device_output`. |

### HTTP Transport

| Field | Type | Default | Env var override | Description |
|---|---|---|---|---|
| `transport` | `string` | `"stdio"` | `NETMIKO_MCP_TRANSPORT` | Transport mode: `stdio` (default) or `streamable-http`. |
| `http_host` | `string` | `"127.0.0.1"` | `NETMIKO_MCP_HTTP_HOST` | Bind address for the HTTP transport. |
| `http_port` | `int` | `8000` | `NETMIKO_MCP_HTTP_PORT` | Listen port for the HTTP transport. |
| `http_path` | `string` | `"/mcp"` | `NETMIKO_MCP_HTTP_PATH` | MCP endpoint path for the HTTP transport. |
| `http_auth_enabled` | `bool` | `true` | `NETMIKO_MCP_HTTP_AUTH_ENABLED` | Enable RFC 6750 bearer token authentication. Should not be disabled on externally reachable deployments. |

The bearer token itself (`NETMIKO_MCP_HTTP_BEARER_TOKEN`) is an environment variable only — it is intentionally not a YAML setting so it cannot be stored in the config file. See [`NETMIKO_MCP_HTTP_BEARER_TOKEN`](#netmiko_mcp_http_bearer_token) below.

### Audit Logging

| Field | Type | Default | Env var override | Description |
|---|---|---|---|---|
| `audit_log_enabled` | `bool` | `true` | `NETMIKO_MCP_AUDIT_LOG_ENABLED` | Enable audit logging. Every MCP tool invocation should produce a structured JSON audit record. Uses a fail-closed policy: if a log write fails, the operation fails. |
| `audit_log_destination` | `string` | `"file"` | `NETMIKO_MCP_AUDIT_LOG_DESTINATION` | Where audit records are written: `file`, `syslog`, or `both`. |
| `audit_log_file` | `string` | `"~/.netmiko_mcp_audit.log"` | `NETMIKO_MCP_AUDIT_LOG_FILE` | Path to the audit log file. Used when `audit_log_destination` is `file` or `both`. Created with mode `0o600`. |
| `audit_log_syslog_address` | `string` | `"/dev/log"` | `NETMIKO_MCP_AUDIT_LOG_SYSLOG_ADDRESS` | Syslog destination: a UNIX socket path (e.g. `/dev/log`) or a `host:port` string for remote UDP syslog. Used when `audit_log_destination` is `syslog` or `both`. |
| `audit_log_syslog_facility` | `string` | `"local0"` | `NETMIKO_MCP_AUDIT_LOG_SYSLOG_FACILITY` | Syslog facility name (e.g. `local0`, `local1`, `daemon`). Used when `audit_log_destination` is `syslog` or `both`. |
| `audit_log_read_transcript` | `bool` | `false` | `NETMIKO_MCP_AUDIT_LOG_READ_TRANSCRIPT` | If `true`, saves the raw SSH channel read transcript to a per-connection file under `audit_log_transcript_dir`. Terminal echo means sent commands are captured in the read stream. |
| `audit_log_transcript_dir` | `string` | `"~/.netmiko_mcp_transcripts"` | `NETMIKO_MCP_AUDIT_LOG_TRANSCRIPT_DIR` | Directory for SSH channel transcript files. Used when `audit_log_read_transcript` is `true`. Created with mode `0o700`; files with mode `0o600`. |
<br />
<br />

## Setting Details

### `inventory_type`

Only `netmiko_tools` is currently supported. The value must be an exact match.

```yaml
inventory_type: "netmiko_tools"
```
<br />

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
<br />
<br />

### `command_file`

Path to your `commands.yml` security whitelist. Defaults to `~/commands.yml`. The full
format and behavior are documented in [commands.md](commands.md).

```yaml
command_file: "~/commands.yml"
```
<br />

### `allow_pipe`

Controls whether pipe operators (`|`) are permitted in commands. `false` by default. When
`true`, only keywords listed in `pipe_modifiers` are accepted after the pipe. Full details
in [commands.md — Pipe Support](commands.md#pipe-support).

```yaml
allow_pipe: false
```
<br />

### `allowed_command_chars`

The complete set of characters permitted in any command string. Any character not in
this set is unconditionally rejected before any other validation. This allowlist approach
is more robust than a blocklist — it handles Unicode space lookalikes and novel injection
characters without enumeration. Full details in [commands.md — Allowed Characters](commands.md#allowed-characters).

The pipe character `|` is intentionally absent. It is added to the effective allowed set
automatically when `allow_pipe` is `true`. Adding `|` here while `allow_pipe` is `false`
is a configuration error raised at startup.

```yaml
allowed_command_chars: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ./:_-,"
```

The default covers: letters, digits, ASCII space, `.` (IP addresses), `/` (prefix lengths,
interface names), `:` (IPv6), `-` and `_` (interface names, VRF names), `,` (VLAN ranges
on NX-OS and Arista). Extend for platform-specific needs.

Environment variable override:
```
NETMIKO_MCP_ALLOWED_COMMAND_CHARS="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ./:_-,"
```
<br />

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
<br />

### `max_workers`

Maximum number of concurrent threads used by `send_show_command_to_group` when querying
multiple devices simultaneously. Each device connection runs in its own thread. Raise this
value for large inventories; lower it to reduce load on the host or on the network devices.

```yaml
max_workers: 10
```
<br />

### `save_output_dir`

Base directory where per-device output files are written. Used by both `send_show_command`
and `send_show_command_to_group` whenever output is saved — whether because `save_output=True`
was passed explicitly, or because the output exceeded `save_threshold` and was auto-saved.
Each device gets its own subdirectory named after the device. The base directory and all
subdirectories are created with mode `0o700`; individual files are created with mode `0o600`.
Tilde expansion is supported.

```yaml
save_output_dir: "~/.netmiko_mcp_tmp"
```
<br />

### `save_threshold`

The line count above which command output is automatically saved to `save_output_dir` instead
of being returned inline to the LLM. Applies to both `send_show_command` (single device) and
`send_show_command_to_group` (per device, when `save_output=False`). When auto-save triggers,
the LLM receives a notification containing the saved filename and instructions to use
`read_device_output` with `offset`/`limit` to retrieve the content incrementally.

The saved filename (not the full path) is included in the notification to avoid exposing
server filesystem layout to the LLM client.

```yaml
save_threshold: 1000
```
<br />
<br />

## HTTP Transport Settings

### `transport`

Selects the MCP transport. `stdio` (the default) spawns the server as a subprocess of the
MCP client and communicates over standard input/output — no network port is opened.
`streamable-http` starts an HTTP server, which is useful for shared deployments or web
clients that cannot spawn a local subprocess.

```yaml
transport: "streamable-http"
```
<br />

### `http_host`

The network address the HTTP server binds to when `transport` is `streamable-http`.
Defaults to `127.0.0.1` (loopback only). Set to `0.0.0.0` only when intentionally
accepting direct external connections — this should always be paired with a reverse proxy
handling TLS and `http_auth_enabled: true`.

```yaml
http_host: "127.0.0.1"
```
<br />

### `http_port`

TCP port the HTTP server listens on when `transport` is `streamable-http`.

```yaml
http_port: 8000
```
<br />

### `http_path`

The URL path at which the MCP endpoint is served when `transport` is `streamable-http`.

```yaml
http_path: "/mcp"
```
<br />

### `http_auth_enabled`

When `true`, every HTTP request must include a valid RFC 6750 `Authorization: Bearer
<token>` header. The token is read from `NETMIKO_MCP_HTTP_BEARER_TOKEN` at startup (see
below). Should remain `true` on any deployment reachable outside localhost.

```yaml
http_auth_enabled: true
```
<br />

### `NETMIKO_MCP_HTTP_BEARER_TOKEN`

The HTTP bearer token is **not** a YAML setting. It is intentionally environment-only so
that it cannot be stored in the config file — secrets belong in the environment, not in
files that may be backed up or shared.

```bash
export NETMIKO_MCP_HTTP_BEARER_TOKEN="$(openssl rand -hex 32)"
```

The server exits at startup if `transport` is `streamable-http`, `http_auth_enabled` is
`true`, and this variable is not set or is empty. Never commit the token to version control
or embed it in a config file.
<br />
<br />

## Audit Logging Settings

### `audit_log_enabled`

When `true`, every MCP tool invocation should produce at least one structured JSON audit
record written to the configured destination. For device commands this is intended to be
two records: one at validation time (verdict and reason) and one after the connection
attempt (outcome). The audit logger is designed to use a fail-closed policy: if a write to
the configured destination fails, the operation should also fail rather than silently
proceeding without a log entry.

```yaml
audit_log_enabled: true
```
<br />

### `audit_log_destination`

Where audit records are written. Valid values:

| Value | Behavior |
|---|---|
| `file` | Write to `audit_log_file` (default) |
| `syslog` | Write to syslog at `audit_log_syslog_address` |
| `both` | Write to both simultaneously |

```yaml
audit_log_destination: "file"
```
<br />

### `audit_log_file`

Path to the local audit log file. Each record is written as a single-line JSON object. The
file is created with mode `0o600`. Parent directories are created automatically. Tilde
expansion is supported. File rotation is left to the operator (e.g. `logrotate`) — the
server appends to the file and does not rotate it.

```yaml
audit_log_file: "~/.netmiko_mcp_audit.log"
```
<br />

### `audit_log_syslog_address`

The syslog destination used when `audit_log_destination` is `syslog` or `both`. Accepts:

- A UNIX socket path: `/dev/log` (Linux default), `/var/run/syslog` (macOS)
- A `host:port` string for remote UDP syslog: `192.0.2.10:514`

```yaml
audit_log_syslog_address: "/dev/log"
```
<br />

### `audit_log_syslog_facility`

Syslog facility name used when sending audit records to syslog. Any standard facility name
is accepted (`local0` through `local7`, `daemon`, `user`, etc.). Defaults to `local0`.

```yaml
audit_log_syslog_facility: "local0"
```
<br />

### `audit_log_read_transcript`

When `true`, the raw bytes read from the SSH channel during each `send_show_command` call
are saved to a file under `audit_log_transcript_dir`. Because network devices echo sent
commands back through the read channel, the transcript captures both sent commands and
received output without needing to tap the write side separately. Passwords and secrets are
filtered by Netmiko's `no_log` mechanism before reaching the buffer.

Transcript filenames follow the pattern `<timestamp>_<correlation_id>_<device>.txt`,
allowing them to be joined with the corresponding audit event records by correlation ID.

```yaml
audit_log_read_transcript: false
```
<br />

### `audit_log_transcript_dir`

Directory where SSH channel transcript files are stored when `audit_log_read_transcript`
is `true`. Created with mode `0o700`; individual transcript files are created with mode
`0o600`. Tilde expansion is supported.

```yaml
audit_log_transcript_dir: "~/.netmiko_mcp_transcripts"
```
<br />
<br />

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

# Allowed command characters (defaults shown)
allowed_command_chars: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ./:_-,"

# Concurrency and output storage
max_workers: 10
save_output_dir: "~/.netmiko_mcp_tmp"
save_threshold: 1000

# HTTP transport (stdio is the default — uncomment to enable HTTP)
# transport: "streamable-http"
# http_host: "127.0.0.1"
# http_port: 8000
# http_path: "/mcp"
# http_auth_enabled: true
# Note: set NETMIKO_MCP_HTTP_BEARER_TOKEN in the environment, not here

# Audit logging (defaults shown)
audit_log_enabled: true
audit_log_destination: "file"
audit_log_file: "~/.netmiko_mcp_audit.log"
# audit_log_syslog_address: "/dev/log"
# audit_log_syslog_facility: "local0"
audit_log_read_transcript: false
audit_log_transcript_dir: "~/.netmiko_mcp_transcripts"
```
<br />
<br />

## Settings Priority

From highest to lowest:

1. **Environment variables** (`NETMIKO_MCP_*`) — always win
2. **`~/.netmiko-mcp.yml`** (or the path in `NETMIKO_MCP_CONFIG`)
3. **Built-in defaults** (shown in the tables above)

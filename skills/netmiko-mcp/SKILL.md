---
name: netmiko-mcp
description: Workflows and configuration references for the Netmiko MCP server, including environment variables, global config (netmiko-mcp.yml), security commands (commands.yml), and running the server over Streamable HTTP transport with bearer token authentication.
---

# Netmiko MCP Server Architecture & Configuration

The Netmiko MCP server exposes network devices to Model Context Protocol clients (like Claude Code) via a highly secure, restricted gateway.

## Global Configuration (`~/.netmiko-mcp.yml`)

The server is configured via a central YAML file.
- **Default Location:** `~/.netmiko-mcp.yml`
- **Override:** Set the `NETMIKO_MCP_CONFIG` environment variable to a custom path.
- **Precedence:** Environment variables starting with `NETMIKO_MCP_` always override keys defined in the YAML file.

### Supported Fields
```yaml
---
inventory_type: "netmiko_tools"          # Optional (Defaults to netmiko_tools. Must be exact match)
# inventory_file: "~/.netmiko.yml"       # Optional. If omitted, uses native Netmiko search paths
command_file: "~/commands.yml"           # Optional (Defaults to ~/commands.yml)
allow_pipe: true                         # Optional (Defaults to false. Enables pipe operators — see Pipe Support below)
unsafe_chars: [";", "\n", "\r", "&"]    # Optional (Defaults to these four — see Unsafe Characters below)
pipe_modifiers: ["include", "exclude", "section", "begin", "count"]  # Optional (Defaults to these five — see Pipe Support below)
```

## Security Whitelist (`~/commands.yml`)

Security relies on an explicit whitelist mapped via the `command_file` property. By default, **all commands are denied**.

Both `allowed_commands` and `denied_commands` use the same exact/glob matching rules:
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

## Pipe Support (`allow_pipe` and `pipe_modifiers`)

`allow_pipe` is `false` by default. Set it to `true` in `~/.netmiko-mcp.yml` or via `NETMIKO_MCP_ALLOW_PIPE=true` to enable pipe operators.

When enabled, the base command is still validated against `allowed_commands`. The first keyword after the pipe is checked against `pipe_modifiers` — anything not in that list is blocked.

### `pipe_modifiers`

Controls which pipe operators are permitted. Default (IOS/IOS-XE):
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

## The Inventory (`~/.netmiko.yml`)

Because the server uses the `netmiko_tools` inventory type, it natively leverages Netmiko's encrypted YAML format.
- Do not expose plaintext credentials in the `list_devices` MCP payload.
- The server requires the `NETMIKO_TOOLS_KEY` environment variable to be exported in the executing shell to perform PBKDF2HMAC decryption of `__encrypt__` fields.

See the `netmiko-tools-yml` skill for a deeper dive into inventory generation and encryption mechanics.

---

## Running the Server over Streamable HTTP

The server supports two transports: `stdio` (default, for MCP clients that launch the process directly) and `streamable-http` (for running as a persistent HTTP service).

### Prerequisites

1. **Install dependencies** (first time only):
   ```bash
   cd /home/mcp_http/pi_mcp_http/netmiko_mcp
   uv sync --python /usr/bin/python3.13
   ```

2. **Copy required config files** from the reference user using `setup_configs.sh`:
   ```bash
   bash setup_configs.sh
   ```
   This copies `commands.yml`, `.netmiko-mcp.yml`, and `.netmiko.yml` into place.
   The server will **hard exit at startup** if `commands.yml` is missing.

### Required Environment Variables

| Variable | Description |
|---|---|
| `NETMIKO_MCP_TRANSPORT` | Set to `streamable-http` to enable HTTP mode (default is `stdio`) |
| `NETMIKO_MCP_HTTP_BEARER_TOKEN` | Secret token for RFC 6750 bearer auth. **Required** when `http_auth_enabled: true` (the default). Server hard exits if missing. |
| `NETMIKO_MCP_CONFIG` | Path to the YAML config file (default: `~/.netmiko-mcp.yml`) |
| `NETMIKO_TOOLS_KEY` | Decryption key for the encrypted Netmiko inventory (`~/.netmiko.yml`) |

#### Generating a Bearer Token

```bash
openssl rand -hex 32
```

This produces a 64-character cryptographically random hex string. Store it only as an environment variable — never in the YAML config file.

#### Setting the Variables

```bash
export NETMIKO_MCP_TRANSPORT="streamable-http"
export NETMIKO_MCP_HTTP_BEARER_TOKEN="<token from openssl rand -hex 32>"
export NETMIKO_MCP_CONFIG="/home/mcp_http/.netmiko-mcp.yml"
export NETMIKO_TOOLS_KEY="<your inventory decryption key>"
```

To persist across sessions, append to `~/.bashrc`:
```bash
echo 'export NETMIKO_MCP_TRANSPORT="streamable-http"' >> ~/.bashrc
echo 'export NETMIKO_MCP_HTTP_BEARER_TOKEN="<your-token>"' >> ~/.bashrc
echo 'export NETMIKO_MCP_CONFIG="/home/mcp_http/.netmiko-mcp.yml"' >> ~/.bashrc
echo 'export NETMIKO_TOOLS_KEY="<your-key>"' >> ~/.bashrc
```

### Optional HTTP Settings

These can be set in `~/.netmiko-mcp.yml` or via environment variables:

```yaml
http_host: "127.0.0.1"   # Bind address. Use 0.0.0.0 to accept external connections.
http_port: 8000           # Port (default: 8000)
http_path: "/mcp"         # MCP endpoint path (default: /mcp)
http_auth_enabled: true   # Enable bearer token auth (default: true — do not disable)
```

To accept connections from other machines:
```bash
export NETMIKO_MCP_HTTP_HOST="0.0.0.0"
```

> **TLS:** TLS termination should be handled by a reverse proxy (nginx, Caddy, etc.). The server runs plain HTTP and relies on the proxy for HTTPS.

### Starting the Server

```bash
cd /home/mcp_http/pi_mcp_http/netmiko_mcp
.venv/bin/netmiko-mcp
```

On successful startup, uvicorn will log:
```
INFO:     Started server process [...]
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

The MCP endpoint is available at:
```
http://<host>:8000/mcp
```

### Connecting an MCP Client

Clients must send requests with the `Authorization` header:
```
Authorization: Bearer <your-token>
```

See `docs/clients/claude-code-http.md` in this repo for Claude Code-specific connection instructions.

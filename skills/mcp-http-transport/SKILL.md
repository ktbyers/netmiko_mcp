---
name: mcp-http-transport
description: HTTP transport for netmiko-mcp — when to use it, SSE vs Streamable HTTP, supported web clients (Claude.ai).
---

> **For humans:** This file is reference documentation for deploying netmiko-mcp over HTTP rather than stdio. It is intended to be read and used by LLMs.

# netmiko-mcp HTTP Transport

## Transport Options

| Transport | When to use |
|---|---|
| `stdio` (default) | Local clients (Claude Code, Desktop, Cursor, etc.) — client spawns server as subprocess, no network port |
| `streamable-http` | Remote/shared deployment, web clients (Claude.ai), multi-user access |

Enable HTTP: set `transport: "streamable-http"` in `~/.netmiko-mcp.yml`. See the `netmiko-mcp` skill for the full config field reference.

---

## Server-Side HTTP Configuration

### Required environment variables

| Variable | Description |
|---|---|
| `NETMIKO_MCP_TRANSPORT` | Set to `streamable-http` to enable HTTP mode |
| `NETMIKO_MCP_HTTP_BEARER_TOKEN` | RFC 6750 bearer token. Required when `http_auth_enabled: true` (the default). Server exits at startup if missing. |
| `NETMIKO_MCP_CONFIG` | Path to config YAML (default: `~/.netmiko-mcp.yml`) |
| `NETMIKO_TOOLS_KEY` | Inventory decryption passphrase (if using encrypted `.netmiko.yml`) |

### Generate a bearer token

```bash
openssl rand -hex 32
```

Store the result as an environment variable only — never in the YAML config file.

### Set variables and start

```bash
export NETMIKO_MCP_TRANSPORT="streamable-http"
export NETMIKO_MCP_HTTP_BEARER_TOKEN="$(openssl rand -hex 32)"
export NETMIKO_MCP_CONFIG="~/.netmiko-mcp.yml"
export NETMIKO_TOOLS_KEY="your-inventory-passphrase"

# Start the server
uv run netmiko-mcp
```

On success, uvicorn logs:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

MCP endpoint: `http://<host>:<port>/mcp` (default: `http://127.0.0.1:8000/mcp`)

### Persist across sessions

```bash
echo 'export NETMIKO_MCP_TRANSPORT="streamable-http"' >> ~/.bashrc
echo 'export NETMIKO_MCP_HTTP_BEARER_TOKEN="<your-token>"' >> ~/.bashrc
echo 'export NETMIKO_MCP_CONFIG="~/.netmiko-mcp.yml"' >> ~/.bashrc
echo 'export NETMIKO_TOOLS_KEY="<your-passphrase>"' >> ~/.bashrc
```

### Optional YAML config overrides

```yaml
http_host: "127.0.0.1"   # Use 0.0.0.0 to accept external connections
http_port: 8000
http_path: "/mcp"
http_auth_enabled: true   # Do not disable in any externally reachable deployment
```

**TLS:** The server runs plain HTTP. Terminate TLS at a reverse proxy.


### Connecting a client

Every request must include the bearer token:
```
Authorization: Bearer <your-token>
```

For Claude Code specifically:
```bash
claude mcp add --transport http netmiko-mcp http://your-server:8000/mcp \
  --header "Authorization: Bearer ${NETMIKO_MCP_HTTP_BEARER_TOKEN}"
```

---

## SSE vs Streamable HTTP

| | **SSE** (legacy) | **Streamable HTTP** (current) |
|---|---|---|
| MCP spec | Pre-2025-03-26 | 2025-03-26+ |
| Endpoints | Two (`/sse` + `/messages`) | One (`/mcp`) |
| Server model | Stateful — holds open connections | Stateless — per-request |
| Resumable streams | ✗ | ✓ |
| CDN / proxy / load balancer | ✗ | ✓ |
| Status | **Deprecated** — vendors dropping through mid-2026 | **Use for all new deployments** |

`netmiko-mcp` implements Streamable HTTP natively and does not expose an SSE endpoint. SSE exists in the underlying FastMCP library but is deprecated and not used.

---

## Web Client Support

Web clients cannot spawn a local subprocess — they need an HTTP endpoint.

| Client | Status | Notes |
|---|---|---|
| **Claude.ai** (web) | ✓ Native | Streamable HTTP via Custom Connectors — no bridge needed |
| **ChatGPT** (web) | ✗ Not recommended | SSE-only transport requires a complex supergateway + ngrok chain; not worth the complexity or security exposure |
| **Perplexity** (web) | ✗ Not working | OAuth 2.1 discovery required; broken as of June 2026; Perplexity is moving away from MCP |
| **Gemini** (gemini.google.com) | ✗ | No MCP support in web UI |

Web-based AI clients are generally not recommended for network device access. Use a desktop or CLI client (Claude Code, Claude Desktop, Cursor, etc.) instead.

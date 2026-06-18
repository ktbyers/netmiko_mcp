# Connecting Claude Desktop to Netmiko MCP via Streamable HTTP

This document describes how to connect Claude Desktop to a self-hosted Netmiko MCP
server running the streamable-http transport. The steps here have been tested with
Claude Desktop and `mcp-remote` as the bridge.

## When to use this setup

Claude Desktop has no native connector for a plain-bearer remote HTTP server. The
`mcp-remote` npm package acts as a local stdio bridge: Claude Desktop spawns it as
a subprocess, and it forwards MCP traffic to the remote HTTP server.

Use this setup when you want Claude Desktop to share the same centrally-hosted
Netmiko MCP server used by Claude Code or other clients.

## Prerequisites

- Node.js installed on the engineer's workstation (required to run `mcp-remote`).
- The Netmiko MCP server deployed and reachable over HTTPS (see the server-side
  configuration in `claude-code-http.md`).
- The bearer token used by the server available as an environment variable on the
  workstation.

## Workstation configuration

Export the bearer token in your shell rc file (`~/.bashrc` or `~/.zshrc`). Do not
put the token value directly in the Claude Desktop config file:

```bash
export NETMIKO_MCP_HTTP_BEARER_TOKEN="your-strong-random-token-here"
```

## Claude Desktop config

Add the server to Claude Desktop's `claude_desktop_config.json`
(`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://your-mcp-server.example.com/mcp",
        "--transport", "http-only",
        "--header", "Authorization:${NETMIKO_MCP_HTTP_BEARER_TOKEN}"
      ]
    }
  }
}
```

Restart Claude Desktop after saving the config. The server should appear in the
connected tools list.

## Non-obvious details

**`--transport http-only`** — By default `mcp-remote` probes for an SSE endpoint
first before falling back to streamable HTTP. The Netmiko MCP server only supports
the streamable-http transport, so the SSE probe fails and the connection is never
established. Passing `--transport http-only` skips the probe entirely.

**`Authorization:${NETMIKO_MCP_HTTP_BEARER_TOKEN}` with no space after the colon**
— `mcp-remote` splits header values on spaces. Passing a literal
`Authorization: Bearer <token>` causes the value to be truncated at the first space,
so the server receives a malformed header and rejects the request. Using an
environment variable reference (`${NETMIKO_MCP_HTTP_BEARER_TOKEN}`) whose value is
the full `Bearer <token>` string, with no space between the header name and value in
the arg itself, avoids the quirk.

## Security notes

- Use a long, randomly generated token (e.g. `openssl rand -hex 32`).
- The token must match the value of `NETMIKO_MCP_HTTP_BEARER_TOKEN` set in the
  server's environment.
- Never commit the token to version control or embed it in the JSON config file
  directly.
- The full MCP specification recommends OAuth 2.0 for remote server authentication.
  The bearer token approach described here is a simpler alternative suitable for
  controlled internal deployments.

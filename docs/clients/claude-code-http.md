# Connecting Claude Code to Netmiko MCP via Streamable HTTP

This document describes how to register the Netmiko MCP server as a remote HTTP
server in Claude Code. The steps here have been tested with the streamable-http
transport added in this project.

## When to use the HTTP transport

The default `stdio` transport spawns the MCP server as a local subprocess. Use the
`streamable-http` transport when:

- You want a single shared server instance accessible by multiple engineers or
  multiple Claude Code sessions simultaneously.
- You are deploying the server on a dedicated host (VM, container, network management
  server) rather than on each engineer's laptop.
- You want centralized audit logging across all sessions.

## Prerequisites

- The `netmiko-mcp` package installed and accessible on the server host.
- A `commands.yml` whitelist file at the path configured by `command_file`
  (default `~/commands.yml`).
- A `~/.netmiko.yml` device inventory on the server host.
- A reverse proxy in front of the server handling TLS.
  The MCP server itself does not terminate TLS — expose it only on localhost
  and let the proxy handle HTTPS.

## Server-side configuration

Set the transport in `~/.netmiko-mcp.yml` on the server host:

```yaml
transport: "streamable-http"
http_host: "127.0.0.1"   # bind to loopback; reverse proxy handles external TLS
http_port: 8000
http_path: "/mcp"
http_auth_enabled: true
```

Export the bearer token as an environment variable in the shell that will run the
server. Do not put the token value in the YAML file:

```bash
export NETMIKO_MCP_HTTP_BEARER_TOKEN="your-strong-random-token-here"
```

Start the server:

```bash
netmiko-mcp
```

The server should log that it is listening on `127.0.0.1:8000`.

## Claude Code client configuration

In your shell rc file (`~/.bashrc` or `~/.zshrc`), export the bearer token that
Claude Code should send with every request:

```bash
export NETMIKO_MCP_HTTP_BEARER_TOKEN="your-strong-random-token-here"
```

Register the remote MCP server in Claude Code:

```bash
claude mcp add netmiko-mcp --transport http https://your-mcp-server.example.com/mcp
```

Claude Code will include the bearer token in the `Authorization` header when
connecting. Verify connectivity:

```bash
claude mcp list
```

The server should appear as connected.

## Security notes

- Use a long, randomly generated token (e.g. `openssl rand -hex 32`).
- The token should be the same value on both the server (`NETMIKO_MCP_HTTP_BEARER_TOKEN`
  set in the server's environment) and in the client's environment for Claude Code.
- Never commit the token to version control or embed it in config files.
- The full MCP specification recommends OAuth 2.0 for remote server authentication.
  The bearer token approach described here is a simpler alternative suitable for
  controlled internal deployments. For public or multi-tenant deployments, a proper
  OAuth 2.0 authorization server should be considered instead.

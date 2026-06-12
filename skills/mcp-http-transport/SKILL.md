---
name: mcp-http-transport
description: HTTP transport for netmiko-mcp — when to use it, SSE vs Streamable HTTP, which web clients work, how to bridge a stdio server over HTTP (supergateway, ngrok), and web client setup for ChatGPT and Perplexity.
---

# netmiko-mcp HTTP Transport

## Transport Options

| Transport | When to use |
|---|---|
| `stdio` (default) | Local clients (Claude Code, Desktop, Cursor, etc.) — client spawns server as subprocess, no network port |
| `streamable-http` | Remote/shared deployment, web clients (Claude.ai), multi-user access |

Enable HTTP: set `transport: "streamable-http"` in `~/.netmiko-mcp.yml`. See the `netmiko-mcp` skill for full config reference.

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

`netmiko-mcp` implements Streamable HTTP natively. SSE exists in FastMCP but is deprecated. When configuring a bridge, target `streamableHttp` over `sse` where the client supports it.

---

## Web Client Support

Web clients cannot spawn a local subprocess — they need an HTTP endpoint. Most require a local `supergateway` bridge. The bridge listens on localhost, so it can only be reached from a browser on the same machine.

| Client | Status | Notes |
|---|---|---|
| **Claude.ai** (web) | ✓ Native | Streamable HTTP via Custom Connectors — no bridge needed |
| **ChatGPT** (web) | ✓ With bridge | Requires `supergateway`; Business plan or higher for full tool access |
| **Perplexity** (web) | ✗ Not working | Requires OAuth 2.1 discovery (`/.well-known/oauth-protected-resource`) — `supergateway` returns 404 |
| **Perplexity** (Mac app) | ✓ stdio | Uses PerplexityXPC helper — see `mcp-client-config` skill |
| **Grok** (x.ai web) | ✓ With bridge | SSE only |
| **Comet** (Perplexity browser) | ✗ | AI browser — not an MCP client |
| **Gemini** (gemini.google.com) | ✗ | No MCP support in web UI |

---

## HTTP Bridge: supergateway

[`supergateway`](https://github.com/supercorp-ai/supergateway) wraps a stdio MCP server and exposes it over SSE or Streamable HTTP. No global install — `npx` runs it directly.

> **Security:** Run on localhost only. Do not expose the bridge port to a network interface — it gives unauthenticated access to your network devices.

> **Direction:** Bridge goes stdio → HTTP. Some tools go the wrong direction (local client → remote HTTP server). Verify before use.

```bash
# SSE on port 8787 (ChatGPT default)
npx -y supergateway --stdio "uv run netmiko-mcp" --outputTransport sse --port 8787

# Streamable HTTP on port 8787 (preferred where supported)
npx -y supergateway --stdio "uv run netmiko-mcp" --outputTransport streamableHttp --port 8787

# With custom config path
npx -y supergateway \
  --stdio "NETMIKO_MCP_CONFIG=/path/to/.netmiko-mcp.yml uv run netmiko-mcp" \
  --outputTransport sse --port 8787
```

Endpoints: `http://localhost:8787/sse` (SSE) or `http://localhost:8787/mcp` (Streamable HTTP).

---

## Adding HTTPS: ngrok

Required for Perplexity (HTTPS-only) and any client that rejects plain HTTP. Free ngrok account is sufficient for testing.

```bash
# Install (macOS)
brew install ngrok

# Install (Windows)
winget install ngrok -s msstore

# Authenticate (one-time)
ngrok config add-authtoken YOUR_TOKEN

# Terminal 1 — start bridge
NETMIKO_MCP_CONFIG="/path/to/.netmiko-mcp.yml" \
  npx -y supergateway --stdio "uv run netmiko-mcp" --outputTransport sse --port 8787

# Terminal 2 — HTTPS tunnel
ngrok http 8787
```

ngrok prints a public HTTPS URL (e.g. `https://abc123.ngrok-free.app`). Use that as the connector endpoint.

---

## ChatGPT Setup

**Plan requirement:** Business or higher for full tool access. Plus is read/fetch only — insufficient for network automation.

| Goal | Plus/Pro | Business | Enterprise/Edu |
|---|---|---|---|
| Register custom MCP app | Read/fetch only | ✓ | ✓ |
| Use write/config tools | ✗ | ✓ | ✓ |

**Steps (after bridge is running on port 8787):**
1. **Settings → Apps → Advanced settings** → toggle **Developer mode** on
2. **Settings → Apps** → **Create app**
3. Enter `http://localhost:8787/sse` as the endpoint URL → Save

> "Connectors" was renamed to "Apps" in December 2025. The UI path above is based on OpenAI documentation but has not been verified hands-on — if **Advanced settings** doesn't show a Developer mode toggle, check [OpenAI's help article](https://help.openai.com/en/articles/12584461).

**Alternative:** OpenAI's [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) — outbound-only relay, no inbound port needed. Most secure option for ChatGPT integration.

---

## Perplexity Status: Not Working (June 2026)

**Web app (Pro+ required):** Probes `/.well-known/oauth-protected-resource` during OAuth 2.1 discovery. `supergateway` returns 404. Connection fails before any MCP messages are exchanged.

**SSE transport:** Returns `[FETCHER_HTML_STATUS_CODE_ERROR]` before reaching the bridge. Root cause unconfirmed — possible path mismatch or plan restriction.

**Perplexity Mac app:** Works via stdio using the PerplexityXPC helper — see `mcp-client-config` skill. This is the viable Perplexity path.

**Open questions:**
- Whether serving a stub `/.well-known/oauth-protected-resource` JSON response unblocks Streamable HTTP
- Whether the correct SSE path is `/sse` or the base URL
- Whether a VPS-hosted server with a real TLS cert changes the outcome

Note: Perplexity's CTO announced in March 2026 the company is moving away from MCP internally — this feature may not be a long-term investment.

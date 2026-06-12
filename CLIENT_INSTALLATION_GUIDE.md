# netmiko-mcp: HTTP Transport and Remote Client Guide

**Last verified: June 2026**

This document covers the HTTP transport for `netmiko-mcp` — when you need it, the difference between SSE and Streamable HTTP, and how to connect web-based clients (ChatGPT, Perplexity) that cannot use stdio.

> **Stdio client setup (Claude Code, Claude Desktop, Cursor, Devin Desktop, VS Code + Copilot, Kiro) and credential management are covered in the `mcp-client-config` skill.**

---

## Table of Contents

- [MCP Transport Protocols](#mcp-transport-protocols)
- [HTTP Transport: SSE vs. Streamable HTTP](#http-transport-sse-vs-streamable-http)
- [Do Web-Based AI Clients Support MCP?](#do-web-based-ai-clients-support-mcp)
- [Installation: ChatGPT](#installation-chatgpt)
- [Installation: Perplexity](#installation-perplexity)
- [HTTP Bridge: supergateway and ngrok](#http-bridge-supergateway-and-ngrok)
- [Sources](#sources)

---

## MCP Transport Protocols

| Protocol | Description |
|---|---|
| **stdio** | Client launches the server as a subprocess; communicates over stdin/stdout. No network port. Local only. Simplest setup. |
| **HTTP (remote)** | Server runs independently and listens on a network endpoint. Required for web-based clients. Enables multi-user, shared deployments. |

`netmiko-mcp` defaults to stdio. HTTP mode is enabled by setting `transport: "streamable-http"` in `~/.netmiko-mcp.yml` — see the `netmiko-mcp` skill for configuration details.

---

## HTTP Transport: SSE vs. Streamable HTTP

The remote HTTP transport has two generations.

### SSE (Server-Sent Events) — Legacy, Deprecated

SSE is a one-directional push channel (server → client only). Because MCP needed two-way communication, the original SSE implementation required two separate HTTP endpoints:

- `/sse` — server pushes responses to the client over a persistent stream
- `/messages` — client POSTs requests to this endpoint

**Problems with the two-endpoint design:**
- Server must hold open a long-lived connection per client — expensive and fragile across load balancers and proxies
- No resumability — if the connection drops, all in-flight state is lost
- Inherently stateful — server must track which SSE connection belongs to which session

### Streamable HTTP — Current Standard

Introduced in MCP spec version 2025-03-26. Replaces both SSE endpoints with **a single HTTP endpoint**. The client POSTs a request; the server responds normally for quick results, or upgrades to on-demand SSE streaming for long-running responses — then closes.

**Advantages:**
- Stateless per-request — no persistent connections to manage
- Resumable streams via event IDs
- Works correctly behind load balancers, CDNs, and reverse proxies
- One endpoint to expose, secure, and route

| | **SSE** (legacy) | **Streamable HTTP** (current) |
|---|---|---|
| MCP spec | Pre-2025-03-26 | 2025-03-26 and later |
| Endpoints | Two (`/sse` + `/messages`) | One |
| Server model | Stateful | Stateless |
| Resumable streams | ✗ | ✓ |
| CDN / proxy friendly | ✗ | ✓ |
| Status | **Deprecated** — vendors dropping through mid-2026 | **Recommended for all new remote deployments** |

> `netmiko-mcp` implements Streamable HTTP. If connecting through an HTTP bridge, target Streamable HTTP. SSE support exists in FastMCP but is deprecated.

---

## Do Web-Based AI Clients Support MCP?

Web-based clients cannot launch a subprocess on your machine, so they can only reach MCP servers exposed over HTTP. Whether they support MCP at all varies:

| Client | Web MCP | Notes |
|---|---|---|
| **Claude.ai** (web) | ✓ Native | Remote MCP via Custom Connectors (Streamable HTTP) — no bridge needed |
| **ChatGPT** (web) | ✓ With bridge | Remote HTTP only; requires `supergateway` to expose `netmiko-mcp` over HTTP |
| **Grok** (x.ai web) | ✓ With bridge | Remote HTTP/SSE only |
| **Perplexity** (web) | ✓ With bridge | Remote HTTPS only; Pro/Max/Enterprise plans; OAuth 2.1 discovery required |
| **Perplexity** (Mac app) | ✓ Native stdio | Local stdio via PerplexityXPC helper — see `mcp-client-config` skill |
| **Comet** (Perplexity browser) | ✗ | AI browser, not an MCP client |
| **Gemini** (gemini.google.com) | ✗ | No MCP support in the web UI |

For `netmiko-mcp` specifically, web GUI access always requires running a local bridge process (`supergateway`) that exposes the stdio server over HTTP. Since the bridge listens on localhost, it can only be reached from a browser on the same machine. The sole exception is Claude.ai, which has native Streamable HTTP connector support and can reach a properly hosted remote endpoint directly.

### Perplexity and Comet: What's the Difference?

**Perplexity web app** (perplexity.ai) — Pro, Max, and Enterprise subscribers can connect via MCP Custom Connectors, but these require remote HTTPS endpoints with OAuth 2.1 compliance. Note: Perplexity's CTO announced in March 2026 that the company is moving away from MCP internally — this feature may not be a long-term priority.

**Perplexity Mac app** — supports local stdio MCP servers via the **PerplexityXPC** helper app, similar to Claude Desktop. This is the viable path for `netmiko-mcp` with Perplexity. See the `mcp-client-config` skill for setup.

**Comet** — Perplexity's AI web browser. It is not an MCP client and cannot call `netmiko-mcp`.

---

## Installation: ChatGPT

> **Plan requirement:** Full MCP support requires **Business or higher.**

ChatGPT supports MCP via remote HTTP endpoints only — it cannot launch local stdio processes. A local HTTP bridge is required.

### Plan requirements

| Goal | Plus / Pro | Business | Enterprise / Edu |
|---|---|---|---|
| Register a custom MCP app | Read/fetch only | ✓ (owner/admin) | ✓ |
| Use write/configuration tools | ✗ | ✓ | ✓ |

ChatGPT Plus is limited to read/fetch MCP tools — insufficient for network automation use cases that may involve config commands.

### Setup

**Step 1 — Run the HTTP bridge** (see [HTTP Bridge section](#http-bridge-supergateway-and-ngrok) below)

**Step 2 — Enable Developer Mode:**
1. Go to **Settings → Apps → Advanced settings**
2. Toggle **Developer mode** on

**Step 3 — Add the custom MCP app:**
1. In **Settings → Apps**, click **Create app**
2. Enter `http://localhost:8787/sse` as the endpoint URL
3. Save

> **Terminology note:** OpenAI renamed "Connectors" to **"Apps"** in December 2025.

> **TODO — Needs verification:** The UI path above is based on OpenAI documentation but has not been successfully verified. If **Settings → Apps → Advanced settings** does not show a Developer mode toggle, the feature may be gated by plan tier or rollout status. Check [OpenAI's help article](https://help.openai.com/en/articles/12584461) for current state.

### Limitations

- The bridge must be running before starting a ChatGPT session
- Bridge listens on localhost — only reachable from a browser on the same machine
- Credentials and device data never leave your machine

---

## Installation: Perplexity

> **Plan requirement:** **Pro or greater** required. Free tier does not expose the custom connector option.

### Testing results — current status: not working

Hands-on testing with a Pro account and an ngrok HTTPS tunnel revealed two blockers:

**Streamable HTTP transport:**
Perplexity probes `/.well-known/oauth-protected-resource` as part of the MCP OAuth 2.1 discovery flow. `supergateway` does not implement this endpoint and returns 404. Connection fails.

**SSE transport:**
Returns `[FETCHER_HTML_STATUS_CODE_ERROR]` before reaching ngrok or `supergateway`. Root cause unclear — may be a path mismatch, an SSE-specific client restriction, or an expired ngrok URL.

**Bottom line:** Perplexity's MCP client requires a fully spec-compliant remote server with OAuth 2.1 discovery. A local `supergateway` bridge is not sufficient. Perplexity is **not a working client for `netmiko-mcp`** in a standard local setup as of June 2026.

> **TODO — Future investigation:**
> - Confirm correct SSE path (`/sse` vs base URL) for Perplexity's SSE transport
> - Determine whether serving a minimal `/.well-known/oauth-protected-resource` JSON response resolves the Streamable HTTP failure
> - Test Cloudflare Tunnel or VPS-hosted `supergateway` with a real TLS cert

### Where to find connector settings

In the Perplexity Mac app: **Customize** in the left navigation pane → Add Connector. (Mac app uses stdio via PerplexityXPC — see `mcp-client-config` skill.)

---

## HTTP Bridge: supergateway and ngrok

`netmiko-mcp` is a stdio server. Clients that require an HTTP endpoint need a bridge that wraps the stdio server and exposes it over HTTP.

> **Direction matters:** The bridge must go stdio → HTTP. Some tools go the wrong direction (connecting a local MCP *client* to a remote HTTP server). Verify direction before using any bridge tool.

> **Security warning:** This exposes your network devices to any process that can reach the bridge endpoint. Run the bridge on localhost only — do not expose it to a network interface.

### Option 1: supergateway (recommended)

[`supergateway`](https://github.com/supercorp-ai/supergateway) wraps a stdio MCP server over SSE or Streamable HTTP with a single command. No global install needed.

```bash
# SSE endpoint on port 8787 (for ChatGPT)
npx -y supergateway --stdio "uv run netmiko-mcp" --outputTransport sse --port 8787

# With custom config path
npx -y supergateway \
  --stdio "NETMIKO_MCP_CONFIG=/path/to/.netmiko-mcp.yml uv run netmiko-mcp" \
  --outputTransport sse --port 8787

# Streamable HTTP (preferred where supported)
npx -y supergateway --stdio "uv run netmiko-mcp" --outputTransport streamableHttp --port 8787
```

Bridge listens at `http://localhost:8787/sse` (SSE) or `http://localhost:8787/mcp` (Streamable HTTP).

### Option 2: OpenAI Secure MCP Tunnel

OpenAI's [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) — an outbound-only relay where a local tunnel client pulls requests from OpenAI and forwards them to your stdio server without exposing a public port. Most secure option — no inbound port needed. See OpenAI's documentation for setup.

### Option 3: MCP Gateway (Docker)

Heavier setup but suitable for shared or persistent deployments. See [Apigene's MCP Gateway guide](https://apigene.ai/blog/deploy-mcp-gateway-docker-5-minutes).

### ngrok for HTTPS

`supergateway` exposes HTTP only. Clients that require HTTPS (Perplexity) need ngrok on top.

**Install ngrok:**
```bash
# macOS
brew install ngrok

# Windows
winget install ngrok -s msstore
```

**Authenticate** (free account at [ngrok.com](https://ngrok.com)):
```bash
ngrok config add-authtoken YOUR_TOKEN
```

**Run bridge + tunnel in two terminals:**
```bash
# Terminal 1 — bridge
NETMIKO_MCP_CONFIG="/path/to/.netmiko-mcp.yml" \
  npx -y supergateway --stdio "uv run netmiko-mcp" --outputTransport sse --port 8787

# Terminal 2 — HTTPS tunnel
ngrok http 8787
```

ngrok prints a public HTTPS URL (e.g. `https://abc123.ngrok-free.app`). Use that as the connector endpoint in Perplexity.

---

## Sources

**Transport protocol and SSE deprecation**
- [MCP Transports — MCP Specification](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [SSE vs Streamable HTTP: Why MCP Switched — Bright Data](https://brightdata.com/blog/ai/sse-vs-streamable-http)
- [MCP SSE Is Deprecated — Chanl Blog](https://www.channel.tel/blog/mcp-sse-to-streamable-http-migration)
- [MCP SSE vs Stdio: Transport Options Explained (2026) — Apigene](https://apigene.ai/blog/mcp-sse-vs-stdio)
- [MCP Transport: stdio vs Streamable HTTP — TrueFoundry](https://www.truefoundry.com/blog/mcp-stdio-vs-streamable-http-enterprise)
- [Why MCP's Move Away from SSE Simplifies Security — Auth0](https://auth0.com/blog/mcp-streamable-http/)

**Client installation and configuration**
- [Building MCP servers for ChatGPT — OpenAI Docs](https://developers.openai.com/api/docs/mcp)
- [How to Use MCP Servers in ChatGPT](https://www.usecarly.com/blog/chatgpt-mcp/)
- [supergateway — GitHub](https://github.com/supercorp-ai/supergateway)
- [PulseMCP client list](https://www.pulsemcp.com/clients)

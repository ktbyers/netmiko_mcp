# MCP Client Transport Support for netmiko-mcp

**Last verified: June 2026**

This document covers which AI coding tools and chat clients support the Model Context Protocol (MCP) stdio and HTTP transports, how they compare, and step-by-step installation instructions for connecting **netmiko-mcp** to popular clients.

> **Note:** This document assumes your AI client is already installed and working. The instructions here focus solely on configuring the netmiko-mcp server within that client. If you need to install the AI client itself, refer to the installation instructions from your respective vendor.

---

## Table of Contents

- [MCP Transport Protocols](#mcp-transport-protocols)
  - [HTTP Transport: SSE vs. Streamable HTTP](#http-transport-sse-vs-streamable-http)
    - [SSE (Server-Sent Events) — Legacy, Deprecated](#sse-server-sent-events-legacy-deprecated)
    - [Streamable HTTP — Current Standard](#streamable-http-current-standard)
- [Clients & Installation](#clients-installation)
  - [Do Web-Based AI Clients Support MCP?](#do-web-based-ai-clients-support-mcp)
    - [Perplexity and Comet: What's the Difference?](#perplexity-and-comet-whats-the-difference)
  - [Client Support Summary](#client-support-summary)
  - [Simplest Setup](#simplest-setup)
  - [Making the Server Available to All Clients](#making-the-server-available-to-all-clients)
  - [A Note on These Instructions](#a-note-on-these-instructions)
    - [Verification Status](#verification-status)
    - [Let the AI do it for you](#let-the-ai-do-it-for-you)
  - [Installation: Claude Code (Reference)](#installation-claude-code-reference)
  - [Installation: Claude Desktop](#installation-claude-desktop)
    - [Option 1: uv tool (recommended)](#option-1-uv-tool-recommended)
    - [Option 2: absolute path to the venv binary](#option-2-absolute-path-to-the-venv-binary)
    - [Why the server may not appear immediately: deferred vs. eager loading](#why-the-server-may-not-appear-immediately-deferred-vs-eager-loading)
    - [Warning: Claude Desktop is unforgiving about its config file](#warning-claude-desktop-is-unforgiving-about-its-config-file)
  - [Installation: Cursor](#installation-cursor)
    - [Config file locations](#config-file-locations)
    - [Config format](#config-format)
    - [Steps](#steps)
    - [Agent mode required for MCP tool calls](#agent-mode-required-for-mcp-tool-calls)
    - [Troubleshooting](#troubleshooting)
  - [Installation: Devin Desktop (formerly Windsurf)](#installation-devin-desktop-formerly-windsurf)
    - [Config file location](#config-file-location)
    - [Config format](#config-format-1)
    - [Steps](#steps-1)
    - [MCP and ACP: Two Layers, One Product](#mcp-and-acp-two-layers-one-product)
    - [Note on Devin Local](#note-on-devin-local)
  - [Installation: VS Code + GitHub Copilot](#installation-vs-code--github-copilot)
    - [Config file locations](#config-file-locations-1)
    - [Config format](#config-format-2)
    - [Steps](#steps-2)
    - [Getting structured JSON output](#getting-structured-json-output)
    - [Troubleshooting](#troubleshooting-1)
  - [Installation: Kiro](#installation-kiro)
    - [Config file locations](#config-file-locations-2)
    - [Config format](#config-format-3)
    - [Steps](#steps-3)
  - [Installation: ChatGPT](#installation-chatgpt)
    - [Plan requirements for ChatGPT MCP](#plan-requirements-for-chatgpt-mcp)
    - [Connecting ChatGPT to the bridge](#connecting-chatgpt-to-the-bridge)
    - [Limitations](#limitations)
  - [Installation: Perplexity](#installation-perplexity)
    - [Where to find the connector settings](#where-to-find-the-connector-settings)
    - [HTTPS requirement — current blocker for local use](#https-requirement--current-blocker-for-local-use)
    - [Perplexity Web App](#perplexity-web-app)
    - [Comet Browser](#comet-browser)
  - [HTTP Bridge: supergateway and ngrok](#http-bridge-supergateway-and-ngrok)
    - [A note on direction](#a-note-on-direction)
    - [Bridge options](#bridge-options)
    - [ngrok for HTTPS](#ngrok-for-https)
- [Secrets](#secrets)
  - [What Does Not Work: Environment Variables in the YAML File](#what-does-not-work-environment-variables-in-the-yaml-file)
  - [Option 1: Netmiko's Built-In Encryption](#option-1-netmikos-built-in-encryption)
    - [Step-by-step walkthrough](#step-by-step-walkthrough)
    - [Encrypting a single password](#encrypting-a-single-password)
    - [Trade-offs](#trade-offs)
  - [Option 2: Generate the Inventory at Startup from a Secrets Manager](#option-2-generate-the-inventory-at-startup-from-a-secrets-manager)
  - [Comparison](#comparison)
  - [What to Avoid](#what-to-avoid)
- [Choosing the Right Client](#choosing-the-right-client)
- [Sources](#sources)

---

## MCP Transport Protocols

MCP servers communicate with clients over one of two transports:

| Protocol          | Description                                                  |
| ----------------- | ------------------------------------------------------------ |
| **stdio**         | The client launches the server as a subprocess and communicates over standard input/output. No network port needed. The simplest setup; inherently local to the machine running the client. |
| **HTTP (remote)** | The server runs as an independent process and listens on a network endpoint. Required for web-based clients and enables multi-user, shared deployments. |

`netmiko-mcp` is a **stdio server**. It is launched by the client directly, runs locally, and does not expose a network port by default. An HTTP deployment requires an additional proxy layer (see the ChatGPT installation section for an example).

---

### HTTP Transport: SSE vs. Streamable HTTP

The remote HTTP transport has two generations. Understanding the difference matters when connecting `netmiko-mcp` to a client that requires an HTTP proxy bridge.

#### SSE (Server-Sent Events) — Legacy, Deprecated

SSE is a standard web technology where a server pushes a continuous stream of events to a browser or client over a single long-lived HTTP connection. You have likely encountered it in live dashboards, log tails, or chat interfaces where the page updates in real time without refreshing.

In the original MCP HTTP implementation, SSE was used as a one-way push channel from the server to the client. Because SSE is one-directional (server → client only), MCP needed a second channel for the client to send requests back. This resulted in **two separate HTTP endpoints**:

- `/sse` — the server opens a persistent stream to push responses to the client
- `/messages` — the client POSTs requests to this endpoint

This two-endpoint design created practical problems:

- The server had to hold open a long-lived connection for every active client — expensive and fragile across load balancers and proxies
- If the connection dropped, all in-flight state was lost (no resumability)
- The server was inherently stateful — it needed to remember which SSE connection belonged to which client session

#### Streamable HTTP — Current Standard

Streamable HTTP, introduced in MCP spec version 2025-03-26, replaces both SSE endpoints with **a single HTTP endpoint**. The client POSTs a request to that endpoint, and the server decides how to respond:

- For a quick, complete response: it returns a normal HTTP response body and closes the connection
- For a long-running or streaming response: it upgrades that same connection to SSE on-demand, streams the events, then closes

The client and server negotiate within a single request/response cycle. No persistent connection needs to be held open between requests.

This matters in practice because:

- **Stateless servers** — each request is self-contained; the server does not need to track open connections
- **Resumable streams** — lost connections can reconnect and pick up where they left off via event IDs
- **Infrastructure compatibility** — works correctly behind load balancers, CDNs, and reverse proxies that would otherwise terminate idle persistent connections
- **Simpler deployment** — one endpoint to expose, secure, and route



| | **SSE** (legacy) | **Streamable HTTP** (current) |
|---|---|---|
| MCP spec | Pre-2025-03-26 | 2025-03-26 and later |
| Endpoints | Two (`/sse` + `/messages`) | One |
| Server model | Stateful (holds open connections) | Stateless |
| Resumable streams | ✗ | ✓ |
| CDN / proxy friendly | ✗ | ✓ |
| Status | **Deprecated** — vendors dropping through mid-2026 | **Recommended for all new remote deployments** |

> **SSE deprecation is underway.** If you are building or configuring a remote HTTP proxy for `netmiko-mcp` today, target Streamable HTTP. The ChatGPT section below covers bridge options and transport considerations.

---


## Clients & Installation

### Do Web-Based AI Clients Support MCP?

Yes, but with limitations, and those limitations directly affect how you connect `netmiko-mcp`.

**Local AI clients** (Claude Desktop, Claude Code, Cursor, Devin Desktop, Gemini CLI, Grok Build, Cline, VS Code + Copilot, and others) support stdio MCP natively. The client launches the server as a subprocess on your machine and communicates over standard input/output. No network port is needed.

**Web-based AI clients** cannot launch a subprocess on your machine, so they can only reach MCP servers exposed over HTTP. Whether they support MCP at all, and how, varies by product:

| Client | Web MCP | Notes |
|---|---|---|
| **Claude.ai** (web) | ✓ Native | Remote MCP via Custom Connectors (Streamable HTTP) — built in, no bridge needed |
| **ChatGPT** (web) | ✓ With bridge | Remote HTTP only; requires `supergateway` to expose `netmiko-mcp` over HTTP |
| **Grok** (x.ai web) | ✓ With bridge | Remote HTTP/SSE only |
| **Perplexity** (web) | ✓ With bridge | Remote HTTPS only; Pro/Max/Enterprise plans; actively moving away from MCP internally |
| **Perplexity** (Mac app) | ✓ Native stdio | Local stdio via PerplexityXPC helper — see note below |
| **Comet** (Perplexity browser) | ✗ as client | Comet is an AI browser, not an MCP client — see note below |
| **Gemini** (gemini.google.com) | ✗ | No MCP support in the web UI |

For `netmiko-mcp` specifically, web GUI access always requires running a local bridge process (`supergateway`) that exposes the stdio server over HTTP — and since the bridge listens on localhost, it can only be reached from a browser on the same machine. The sole exception is Claude.ai, which has native Streamable HTTP connector support and can reach a properly hosted remote MCP endpoint directly.

For the simplest web GUI experience, Claude.ai is the recommended path.

#### Perplexity and Comet: What's the Difference?

Perplexity offers three distinct products that behave very differently for MCP:

**Perplexity web app** (perplexity.ai) is an AI-powered search and assistant platform comparable to ChatGPT or Claude.ai. As of March 2026, Pro, Max, and Enterprise subscribers can connect it to external tools via MCP Custom Connectors, but these accept remote HTTPS endpoints only — no local stdio support. Also worth noting: Perplexity's CTO publicly announced in March 2026 that the company is moving away from MCP internally in favor of REST APIs and CLIs, so this feature may not be a long-term priority.

**Perplexity Mac app** is a native macOS application that supports local stdio MCP servers via a helper app called **PerplexityXPC**. Because Mac App Store apps run in a sandbox, the XPC helper bridges the gap and allows the Perplexity app to launch and communicate with local MCP servers similar to how Claude Desktop works. This makes the Mac app a viable client for `netmiko-mcp`.

To set it up: install PerplexityXPC (prompted the first time you add a connector), then go to **Connectors settings → Add Connector** and provide the server name and the command to launch the server (`uv run netmiko-mcp`).

**Comet** is a full web browser built by Perplexity. It is a replacement for Chrome or Safari with AI woven into the browsing experience. It helps with in-page research, summarization, and comparison as you browse. Comet is **not** an MCP client and does not call MCP tool servers on your behalf.

> **Nuance:** Third-party community MCP servers (such as [Perplexity-Comet-MCP](https://github.com/RapierCraft/Perplexity-Comet-MCP)) exist that let Claude Code *control* the Comet browser as a browsing tool. This is the reverse direction — Comet becomes a tool that Claude uses, not a client that calls `netmiko-mcp`.

**Summary for netmiko-mcp:**

| Product | Usable? | Notes |
|---|---|---|
| Perplexity web | Possible but impractical | Remote HTTPS only, paid plan, MCP being deprioritized internally |
| Perplexity Mac app | ✓ Yes | Local stdio via PerplexityXPC helper — viable path |
| Comet browser | No | Not an MCP client |

---

### Client Support Summary

| Client | stdio | HTTP (Streamable) | Notes |
|---|---|---|---|
| **Claude Desktop** | ✓ | ✓ | Remote via Custom Connectors; JSON config for stdio |
| **Claude Code (CLI)** | ✓ | ✓ | `claude mcp add --transport http <url>` for remote |
| **Cursor** | ✓ | ✓ | Streamable HTTP + SSE fallback (fallback has known bug — see below) |
| **Devin Desktop** (formerly Windsurf) | ✓ | ✓ | ACP multi-agent layer sits above MCP; both transports supported |
| **Kiro** (AWS IDE) | ✓ | ✓ | Streamable HTTP + SSE fallback; excellent native MCP docs and server directory |
| **VS Code + GitHub Copilot** | ✓ | ✓ | Agent mode only; GA since VS Code 1.102 |
| **Cline** | ✓ | ✓ | VS Code, JetBrains, Cursor, Zed, Neovim, CLI preview |
| **Continue.dev** | ✓ | ✓ | VS Code + JetBrains; MCP added in v0.9 |
| **Gemini CLI** | ✓ | ✓ | stdio + SSE + Streamable HTTP; OAuth 2.0 for remote servers |
| **Grok Build** (xAI CLI) | ✓ | — | stdio-focused; zero-reconfiguration from Claude Code/Cursor configs; HTTP remote unclear |
| **Amazon Q Developer** | ✓ | ✓ | IDE plugin (VS Code, JetBrains); verify current AWS support status |
| **Zed** | ✓ | partial | stdio solid; Streamable HTTP in progress per community reports |
| **LM Studio** | ✓ | — | Local LLM desktop app; HTTP remote support unclear |
| **Perplexity** (Mac app) | ✓ | — | Local stdio via PerplexityXPC helper; similar setup to Claude Desktop |
| **ChatGPT** | ✗ | ✓ | Streamable HTTP only; requires `supergateway` bridge to reach a stdio server |
| **Perplexity** (web) | ✗ | ✓ | Remote HTTPS only; Pro/Max/Enterprise; actively deprioritizing MCP internally |
| **Grok API** | ✗ | ✓ (SSE) | Legacy SSE remote only; no stdio; Streamable HTTP support unconfirmed |
| **Gemini web** (gemini.google.com) | ✗ | ✗ | No MCP support in the web UI |
| **Comet** (Perplexity browser) | ✗ | ✗ | AI browser, not an MCP client |

**Legend:** ✓ confirmed supported · ✗ not supported · partial = works with caveats · — = unknown/unconfirmed

> **Note on Amazon Q:** AWS has announced an end-of-support timeline for Amazon Q Developer — verify current status in AWS docs before relying on it.

> **Note on Cursor HTTP fallback:** A reported bug causes Cursor to fail falling back from Streamable HTTP to SSE for remote servers. If connecting Cursor to an SSE-only remote server, pin the transport explicitly in your config rather than relying on auto-negotiation.

---

### Simplest Setup

The server has sensible defaults for all file locations. If you place your files in the home directory using the default names, no environment variables or extra client configuration are needed:

| File | Default path |
|---|---|
| MCP server config | `~/.netmiko-mcp.yml` |
| Device inventory | `~/.netmiko.yml` |
| Commands whitelist | `~/commands.yml` |

Every client config shown in this document will work as-is with no `env` block when these defaults are in place. Custom file locations require passing `NETMIKO_MCP_CONFIG` to the client — covered in each installation section below.

---

### Making the Server Available to All Clients

How you install `netmiko-mcp` determines which clients can launch it.

**`uv pip install -e .`** (source install) puts the executable only in the project's local `.venv`. Claude Code finds it because it runs from the project directory. Every other client, Claude Desktop, Cursor, Devin Desktop, Gemini CLI, launches the server subprocess from its own working directory and will fail with a "No such file or directory" error.

**`uv tool install`** makes `netmiko-mcp` available globally so any client can launch it regardless of working directory. This is required for all clients other than Claude Code.

Install from PyPI (Future):

```bash
uv tool install netmiko-mcp
```

Install from a local source checkout (editable):

```bash
uv tool install -e /path/to/netmiko_mcp
```

Verify the tool is registered:

```bash
uv tool list
```

`netmiko-mcp` should appear in the output. Once installed as a tool, the `uv run netmiko-mcp` command in any client config resolves correctly.

---

### A Note on These Instructions

The installation steps in this document reflect what worked as of **June 2026**. The AI client landscape is moving exceptionally fast. UI paths change, features get renamed or moved, plan tiers shift, and new clients appear regularly. Instructions that are accurate today may be outdated within weeks or months.

**Before following any section here, check the client's own documentation first.** Most clients now have dedicated MCP setup guides that will reflect their current UI and requirements more accurately than any third-party document can.

#### Verification Status

The following table reflects actual hands-on testing as of June 2026. "Verified" means the full end-to-end flow was tested — server started, tools loaded, and a command executed against a real device.

| Client | Status | Notes |
|---|---|---|
| **Claude Code** | ✓ Verified | Full end-to-end tested |
| **Claude Desktop** | ✓ Verified | Full end-to-end tested |
| **Cursor** | ✓ Verified | Agent mode required |
| **Devin Desktop** (formerly Windsurf) | ✓ Verified | Agent mode / Cascade required |
| **VS Code + GitHub Copilot** | ✓ Verified | Free tier sufficient;  use "structured data" phrasing for TextFSM parsing |
| **Kiro** (AWS IDE) | — Not tested | Instructions based on documentation only |
| **ChatGPT** | ✗ Not working | **Business or higher required** for full MCP including write/config tools. Plus has developer mode but read/fetch only — insufficient for `netmiko-mcp` |
| **Perplexity** | ✗ Not working | **Pro or higher required** — free tier cannot configure MCP. Pro account + ngrok HTTPS tested: Streamable HTTP fails on OAuth discovery (404 on `/.well-known/oauth-protected-resource`); SSE fails before reaching server |
| **All other clients** | — Not tested | Instructions based on documentation only |

#### Let the AI do it for you

One of the best ways to navigate rapidly changing client UIs is to ask the AI client itself. If you are already inside a working client (Claude Code, Cursor, Devin Desktop), you can paste this document or describe what you need and ask the AI to find the current setting, write the config, or run the registration command for you.

For example, in Claude Code:

> "Add netmiko-mcp as a local MCP server. The command is `uv run netmiko-mcp` and the config file is at `/path/to/.netmiko-mcp.yml`."

Claude Code will run `claude mcp add` with the right flags and confirm it worked. For other clients, the AI can often locate the correct settings panel, generate the JSON config, and talk you through steps that may have changed since this document was written.

---

### Installation: Claude Code (Reference)

Claude Code is the simplest client and the recommended way to develop with `netmiko-mcp`.

**Basic registration (uses default config path `~/.netmiko-mcp.yml`):**

```bash
# Project scope — active in this directory only (two equivalent forms)
claude mcp add netmiko-mcp -- uv run netmiko-mcp
claude mcp add -s local netmiko-mcp -- uv run netmiko-mcp

# User scope — available in all your projects
claude mcp add -s user netmiko-mcp -- uv run netmiko-mcp
```

**Pointing Claude Code at a specific config file:**

If your `netmiko-mcp.yml` lives somewhere other than `~/.netmiko-mcp.yml`, pass `NETMIKO_MCP_CONFIG` using the `-e` flag at registration time. Claude Code stores the env var in `~/.claude.json` alongside the server entry and injects it into the server process on every launch.  You do not need to export it in your shell.

```bash
claude mcp add -s user \
  -e NETMIKO_MCP_CONFIG="/path/to/.netmiko-mcp.yml" \
  netmiko-mcp -- uv run netmiko-mcp
```

If your inventory also uses encrypted credentials, add `NETMIKO_TOOLS_KEY` in the same command:

```bash
claude mcp add -s user \
  -e NETMIKO_MCP_CONFIG="/path/to/.netmiko-mcp.yml" \
  -e NETMIKO_TOOLS_KEY="your_passphrase" \
  netmiko-mcp -- uv run netmiko-mcp
```

**To remove:**

```bash
claude mcp remove netmiko-mcp -s local
claude mcp remove netmiko-mcp -s user
```

Verify the server is running:

```
> ping
 Server is up — pong.
```

---

### Installation: Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows).

Unlike Claude Code, Claude Desktop has no `-e` flag or `claude mcp add` command env vars must be set directly in the JSON config file. This is how you wire up your config file path and any other server settings.

#### Option 1: uv tool (recommended)

Requires `netmiko-mcp` to be installed as a global `uv` tool (see [Making the Server Available to All Clients](#making-the-server-available-to-all-clients)). Claude Desktop calls `uv run netmiko-mcp` and `uv` resolves the command regardless of working directory.

**Default config (uses `~/.netmiko-mcp.yml`):**

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "uv",
      "args": ["run", "netmiko-mcp"]
    }
  }
}
```

**With a custom config file location:**

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "uv",
      "args": ["run", "netmiko-mcp"],
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml"
      }
    }
  }
}
```

#### Option 2: absolute path to the venv binary

If you installed from source with `uv pip install -e .` and do not want to install as a global tool, point `command` directly at the executable in the project's virtual environment. This avoids the global install step but is brittle as the path breaks if you move or rename the repo.

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "/path/to/netmiko_mcp/.venv/bin/netmiko-mcp",
      "args": [],
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml"
      }
    }
  }
}
```

Replace `/path/to/netmiko_mcp` with the absolute path to your local clone. To find it:

```bash
find ~ -path "*netmiko_mcp/.venv/bin/netmiko-mcp" 2>/dev/null
```

---

If your inventory uses encrypted credentials, add `NETMIKO_TOOLS_KEY` to the `env` block of whichever option you use:

```json
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml",
        "NETMIKO_TOOLS_KEY": "your_passphrase"
      }
```

**Restart Claude Desktop**. Go to Settings -> Developer to get stats of the MCP server after restart or simply ask Claude "What is the status of my Netmiko MCP server?".

#### Why the server may not appear immediately: deferred vs. eager loading

Registering a server in `claude_desktop_config.json` does not mean its tools are available from the first message of a conversation. Claude Desktop loads MCP servers in two ways:

| Load Style      | Description                                                  |
| --------------- | ------------------------------------------------------------ |
| Eagerly loaded  | Tools are available immediately at the start of the conversation. Some built-in integrations (Google Calendar, Gmail, Google Drive) work this way. |
| Deferred loaded | The server is registered and available but not fully initialized until the tool is actually needed. `netmiko-mcp` is deferred loaded. The full tool schema and parameter definitions are fetched on demand rather than upfront. |



This is an efficiency trade-off: fully loading every registered MCP server at conversation start would consume memory and context space even for servers that never get used. Deferring means the cost is only paid when the tool is relevant.

In practice this means: being in `claude_desktop_config.json` means the server is *registered*, not necessarily *pre-loaded*. The first time you ask Claude to do something that involves network devices, it will load the tool schema automatically. You may see a brief pause on that first call and this is normal.

> **Note:** This deferred vs. eager loading behavior is specific to Claude Desktop. Other clients — Cursor, Devin Desktop, VS Code + GitHub Copilot, Kiro — generally load MCP servers at startup when the client launches, so tools are available from the first message without a warm-up pause. The tradeoff is that those clients pay the token cost of loading tool schemas on every session, whether the tools are used or not. Claude Desktop's deferred approach only pays that cost when the tools are actually needed.

---

#### Warning: Claude Desktop is unforgiving about its config file

Claude Desktop validates `claude_desktop_config.json` on every launch. If it finds any problem, say a JSON syntax error, a trailing comma, an unmatched brace, it silently discards the entire file and reverts to a clean default, taking your `mcpServers` block with it. It does not warn you, show an error, or keep a backup. **The file simply returns to its pre-edit state** and the MCP server never appears.

Practical rules:
- **Always validate your JSON before saving.** Paste the file contents into a JSON validator (or run `python3 -m json.tool claude_desktop_config.json` in a terminal) before restarting Claude Desktop.
- **Do not hand-edit the file while Claude Desktop is running.** Claude Desktop may overwrite your changes when it exits.
- **If your MCP server disappears after a restart**, check the file. It has almost certainly been reverted. Open it and look for the `mcpServers` key; if it is gone, the file was reset.
- **The MCP server log** (`~/Library/Logs/Claude/mcp*.log` on macOS) is the most reliable place to see what actually went wrong — it captures startup errors from the server process that are not surfaced in the UI.

---

### Installation: Cursor

Cursor supports stdio MCP servers natively via a JSON config file. Configurations are scoped to a project or globally to your user.

#### Config file locations

| Scope | Path |
|---|---|
| Project | `.cursor/mcp.json` (in repo root) |
| Global (all projects) | `~/.cursor/mcp.json` |

#### Config format

Default config (uses `~/.netmiko-mcp.yml`):

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "uv",
      "args": ["run", "netmiko-mcp"]
    }
  }
}
```

With a custom config file location:

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "uv",
      "args": ["run", "netmiko-mcp"],
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml"
      }
    }
  }
}
```

If your inventory also uses encrypted credentials, add `NETMIKO_TOOLS_KEY` to the same `env` block:

```json
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml",
        "NETMIKO_TOOLS_KEY": "your_passphrase"
      }
```

#### Steps

1. Open Cursor Settings (`Cmd+,` on macOS / `Ctrl+,` on Windows).
2. Navigate to **Tools & MCPs**.
3. Create or edit `.cursor/mcp.json` in your project root (or `~/.cursor/mcp.json` for global scope) with the config above.
4. Restart Cursor.

Cursor will launch the server subprocess automatically when you open the project. You can verify it loaded under **Settings > Tools & MCPs** — active servers are listed with a green indicator.

#### Agent mode required for MCP tool calls

Cursor has two chat modes: **Ask** and **Agent**. MCP tool calls including a simple health check like `ping` are only available in **Agent mode**.  At this time, Ask mode blocks all MCP tool execution even for read-only operations.

To use `netmiko-mcp` in Cursor, switch to Agent mode before making any requests. The mode selector is in the chat input area. If a tool appears available but Cursor refuses to call it, this is almost always the cause.

#### Troubleshooting

- Copy the `command` + `args` verbatim and run them in a terminal to surface startup errors Cursor may suppress.
- Ensure `uv` is on your `PATH` (run `uv --version` in the terminal Cursor uses).
- If the server doesn't show up under **Settings > Tools & MCPs**, restart Cursor fully (not just reload window).
- If tools are listed but calls are blocked, confirm you are in **Agent mode**, not Ask mode.

---

### Installation: Devin Desktop (formerly Windsurf)

Windsurf was rebranded as **Devin Desktop** on June 2, 2026. The IDE is the same product; existing Windsurf settings, extensions, keybindings, and MCP configurations migrate automatically. The `~/.codeium/` directory structure is unchanged.

#### Config file location

| Platform | Path |
|---|---|
| macOS / Linux | `~/.codeium/windsurf/mcp_config.json` |
| Windows | `%USERPROFILE%\.codeium\windsurf\mcp_config.json` |

#### Config format

Default config (uses `~/.netmiko-mcp.yml`):

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "uv",
      "args": ["run", "netmiko-mcp"]
    }
  }
}
```

With a custom config file location:

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "uv",
      "args": ["run", "netmiko-mcp"],
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml"
      }
    }
  }
}
```

If your inventory also uses encrypted credentials, add `NETMIKO_TOOLS_KEY` to the same `env` block:

```json
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml",
        "NETMIKO_TOOLS_KEY": "your_passphrase"
      }
```

#### Steps

1. Open or create `~/.codeium/windsurf/mcp_config.json`.
2. Add the `netmiko-mcp` entry above.
3. Restart Devin Desktop.
4. Switch to **Agent mode** (as opposed to Editor mode). The AI chat panel is labeled **Cascade** and remains so even after the Windsurf → Devin Desktop rebrand (as of this writing).
5. Verify the server loaded by asking Cascade to ping `netmiko-mcp` or list devices.

If you cannot find the MCP server status in settings, simply ask in the Cascade chat.  It will confirm whether the tool is available and can call it directly.

#### MCP and ACP: Two Layers, One Product

Devin Desktop operates at two distinct protocol layers:

| Protocol                     | Description                                                  |
| ---------------------------- | ------------------------------------------------------------ |
| MCP (Model Context Protocol) | The layer this document covers. MCP is the open standard for giving AI models access to external tools and data. `netmiko-mcp` is an MCP server. This is where device connections, show commands, and device listing happen. |
| ACP (Agent Client Protocol)  | A higher-level protocol developed by Cognition AI (the makers of Devin) for coordinating between multiple AI agents. Where MCP lets a single AI call tools, ACP lets multiple AI agents hand off work to each other, share context, and collaborate on a task. For example, a planning agent could delegate a network audit subtask to another agent that uses `netmiko-mcp` to collect data. |



#### Note on Devin Local

Devin Desktop introduced **Devin Local**, a local agent mode that can drive MCP tools autonomously. `netmiko-mcp` works with Devin Local the same way as with the standard Agent mode workflow.

---

### Installation: VS Code + GitHub Copilot

VS Code + GitHub Copilot supports stdio MCP natively and has been GA since VS Code 1.102. The **free GitHub Copilot tier is sufficient** — no paid subscription is required for basic tool use including ping and show commands.

#### Config file locations

VS Code uses `"servers"` (not `"mcpServers"`) and requires an explicit `"type"` field — unlike every other client in this guide.

| Scope | Path |
|---|---|
| Workspace | `.vscode/mcp.json` (in repo root) |
| User (all projects) | User `settings.json` under `"mcp"` → `"servers"` |

#### Config format

**Workspace scope** — create `.vscode/mcp.json` in your project root:

Default config (uses `~/.netmiko-mcp.yml`):

```json
{
  "servers": {
    "netmiko-mcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "netmiko-mcp"]
    }
  }
}
```

With a custom config file location:

```json
{
  "servers": {
    "netmiko-mcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "netmiko-mcp"],
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml"
      }
    }
  }
}
```

**User scope** — open user `settings.json` (`Cmd+Shift+P` → **Open User Settings (JSON)**) and add:

```json
{
  "mcp": {
    "servers": {
      "netmiko-mcp": {
        "type": "stdio",
        "command": "uv",
        "args": ["run", "netmiko-mcp"]
      }
    }
  }
}
```

If your inventory uses encrypted credentials, add `NETMIKO_TOOLS_KEY` to the `env` block of whichever config you use:

```json
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml",
        "NETMIKO_TOOLS_KEY": "your_passphrase"
      }
```

#### Steps

1. Create `.vscode/mcp.json` in your project root (workspace scope) or open user `settings.json` for global scope.
2. Add the `netmiko-mcp` entry above.
3. Reload VS Code (`Cmd+Shift+P` → **Developer: Reload Window**).
4. Open the **Copilot Chat** panel and ask: *"Ping the netmiko-mcp server"* — it should respond `pong`.

You can also confirm the server is active via **Command Palette → MCP: List Servers**, which shows registered servers and their status.

#### Getting structured JSON output

Prompt phrasing matters when asking for parsed output. "In JSON format" alone is often not sufficient to trigger TextFSM parsing. Use **"structured data"** to reliably invoke `use_textfsm=True`:

> "Execute `show vlan` on all the devices in my NetMiko inventory. I need the output in JSON and save the output as structured data JSON files with the switch name.json in the current working directory."

#### Troubleshooting

- If the server doesn't appear in **MCP: List Servers**, confirm `.vscode/mcp.json` is valid JSON and `uv` is on the PATH VS Code uses (run `uv --version` in the VS Code integrated terminal).
- VS Code's **Output panel → GitHub Copilot** shows MCP server startup errors not surfaced in the chat UI.

---

### Installation: Kiro

[Kiro](https://kiro.dev) is an AI IDE from AWS — think Cursor or VS Code with an AI agent layer built in — aimed particularly at developers working in AWS environments. Like Cursor, Kiro is an editor-first tool: you write code, and the AI agent can access your codebase, run terminal commands, and call MCP tools as part of its workflow. It supports the full MCP stdio transport natively, making `netmiko-mcp` a straightforward fit.

Kiro has some of the **best MCP documentation** of any client. The [MCP docs](https://kiro.dev/docs/mcp/) are thorough and well-organized, covering configuration, troubleshooting, enterprise governance, and a [server directory](https://kiro.dev/docs/mcp/servers/) listing compatible servers. If in doubt about any step below, the official Kiro MCP docs are the first place to check — they are actively maintained and more likely to be current than any third-party guide.

#### Config file locations

Kiro uses the same config file at two scopes:

| Scope | Path |
|---|---|
| Global (all projects) | `~/.kiro/settings/mcp.json` |
| Project | `.kiro/settings/mcp.json` (in repo root) |

#### Config format

Default config (uses `~/.netmiko-mcp.yml`):

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "uv",
      "args": ["run", "netmiko-mcp"]
    }
  }
}
```

With a custom config file location:

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "uv",
      "args": ["run", "netmiko-mcp"],
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml"
      }
    }
  }
}
```

If your inventory uses encrypted credentials, add `NETMIKO_TOOLS_KEY` to the same `env` block:

```json
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml",
        "NETMIKO_TOOLS_KEY": "your_passphrase"
      }
```

#### Steps

1. Open or create `~/.kiro/settings/mcp.json` (global) or `.kiro/settings/mcp.json` in your project root.
2. Add the `netmiko-mcp` entry above.
3. Restart Kiro.
4. Verify the server loaded by asking the Kiro agent to ping `netmiko-mcp` or list devices.

If the server does not appear, Kiro's MCP settings panel will show the server status and any startup errors. You can also copy the `command` + `args` and run them in a terminal to surface errors that Kiro may suppress.

---

### Installation: ChatGPT

> **Plan requirement:** Full MCP support requires **Business or higher**. See the plan breakdown below.

ChatGPT supports MCP only via **remote HTTP endpoints** — it cannot launch local stdio processes. To use `netmiko-mcp` with ChatGPT, you must run a local HTTP bridge that proxies stdio over HTTP.

#### Plan requirements for ChatGPT MCP

OpenAI gates MCP capability by plan tier. Developer mode is available on Plus and Pro, but full MCP — including write and modify actions — is limited to Business, Enterprise, and Edu. As of June 2026:

| Goal | Plus / Pro | Business | Enterprise / Edu |
|---|---|---|---|
| Run `netmiko-mcp` locally | ✓ | ✓ | ✓ |
| Enable developer mode in ChatGPT | ✓ | ✓ | ✓ |
| Register a custom MCP app in ChatGPT | Read/fetch only | ✓ (owner/admin) | ✓ (authorized devs) |
| Use write/configuration tools in ChatGPT | ✗ | ✓ | ✓ |
| Create an OpenAI Secure Tunnel (API) | Potentially, with separate API billing | ✓ | ✓ |

**ChatGPT Plus** has developer mode but is limited to read/fetch MCP tools. Because `netmiko-mcp` can send configuration commands to network devices, Plus is not sufficient for full use.

**ChatGPT Business** is the practical minimum for network automation. As the workspace owner or admin you enable developer mode and register the server. Business pricing dropped to $20/seat/month (annual) in April 2026.

**OpenAI Secure MCP Tunnel** (see Option 2 in Bridge options below) is accessible via the API regardless of ChatGPT plan, but API usage is billed separately. This path works for API-based applications and Codex but does not give you the ChatGPT chat interface.

If you do not have a Business or Enterprise account, the most practical alternatives are Claude Desktop, Cursor, or Devin Desktop — all of which support `netmiko-mcp` natively without plan restrictions.

> **Security warning:** This exposes your network devices to any process that can reach the bridge endpoint. Run the bridge on localhost only and do not expose it to a network interface.


#### HTTP Bridge Setup

ChatGPT requires an HTTP endpoint — `netmiko-mcp` cannot be reached directly. You must run a local bridge that exposes the stdio server over HTTP. See [HTTP Bridge: supergateway and ngrok](#http-bridge-supergateway-and-ngrok) below for full setup instructions, then return here to connect ChatGPT to the running bridge.

#### Connecting ChatGPT to the bridge

> **Terminology note:** OpenAI renamed "Connectors" to **"Apps"** in December 2025. If you see "Apps" in the UI, that is the same feature. Some documentation still uses the old name.

> **TODO — Needs verification:** The UI path below is based on OpenAI documentation but has not been successfully verified with a Plus account. If **Settings → Apps → Advanced settings** does not show a Developer mode toggle, the feature may be gated differently by plan tier, region, or rollout status. Check [OpenAI's help article](https://help.openai.com/en/articles/12584461) for the current state and report back so this section can be updated.

**Step 1 — Enable Developer Mode:**

1. Go to **Settings → Apps → Advanced settings**.
2. Toggle **Developer mode** on.

**Step 2 — Add the custom MCP app:**

1. Still in **Settings → Apps**, click **Create app** (appears next to Advanced settings after Developer Mode is enabled).
2. Enter `http://localhost:8787/sse` as the endpoint URL.
3. Save and confirm the app appears in the list.

The app will now be available as a tool in the ChatGPT composer during conversations.

#### Limitations

- The bridge must be running before starting a ChatGPT session.
- Because the bridge runs on your machine, it is only reachable from a browser session on that same machine (localhost).
- Credentials and device data never leave your machine, but the bridge itself is an extra process to manage.

---

### Installation: Perplexity

> **Plan requirement:** A **Pro or greater** account is required. The free tier does not expose the custom connector option — if you cannot find it, the account plan is the reason.

#### Where to find the connector settings

In the Perplexity Mac app, MCP connectors are configured via **Customize** in the left navigation pane. Within Customize, you will find the option to add a custom connector.

#### Testing results — current status: not working

Hands-on testing with a Pro account and an ngrok HTTPS tunnel revealed two blockers:

**Streamable HTTP transport:**
Perplexity probes `/.well-known/oauth-protected-resource` as part of the MCP OAuth 2.1 discovery flow. `supergateway` does not implement this endpoint and returns 404. Perplexity fails the connection.

**SSE transport:**
The connection attempt returned `[FETCHER_HTML_STATUS_CODE_ERROR]` and produced no log entry on the server — the request failed on Perplexity's side before reaching ngrok or `supergateway`. Root cause unclear; may be a path mismatch (Perplexity may expect the full `/sse` path explicitly), an expired ngrok URL, or an SSE-specific client restriction.

**Bottom line:** Perplexity's MCP client appears to require a fully spec-compliant remote MCP server — one that correctly handles OAuth discovery and authentication flows. A local `supergateway` bridge is not sufficient. Perplexity is **not a working client for `netmiko-mcp`** in a standard local setup as of June 2026.

> **TODO — Future investigation:**
> - Confirm the correct SSE path (`/sse` vs base URL) for Perplexity's SSE transport
> - Determine whether serving a minimal `/.well-known/oauth-protected-resource` JSON response (e.g. via a small proxy in front of `supergateway`) resolves the Streamable HTTP failure
> - Consider whether Cloudflare Tunnel or a VPS-hosted `supergateway` with a real TLS cert changes the outcome

For ngrok setup details, see [HTTP Bridge: supergateway and ngrok — ngrok for HTTPS](#ngrok-for-https) below.

#### Perplexity Web App

Same HTTPS constraint applies. The web app accepts remote HTTPS MCP endpoints only and cannot launch local processes. Not a practical path for local network automation.

Note also that Perplexity's CTO announced in March 2026 that the company is moving away from MCP internally in favor of REST APIs and CLIs — this feature may not be a long-term investment for them.

#### Comet Browser

Comet is Perplexity's AI web browser. It is not an MCP client and cannot call `netmiko-mcp`. See [Perplexity and Comet: What's the Difference?](#perplexity-and-comet-whats-the-difference) for more context.

---


---

### HTTP Bridge: supergateway and ngrok

`netmiko-mcp` is a stdio server. Clients that require an HTTP endpoint (ChatGPT, Perplexity) need a bridge that wraps the stdio server and exposes it over HTTP. This section covers the two tools needed: **supergateway** for the stdio→HTTP translation, and **ngrok** to add HTTPS on top.

#### A note on direction

The bridge must go in the right direction: **stdio → HTTP**. `netmiko-mcp` is a stdio server; ChatGPT needs an HTTP endpoint. The bridge wraps the stdio server and exposes it over HTTP.

Note that some tools with "remote" or "proxy" in their name go the *wrong* direction — connecting a local MCP *client* to a remote HTTP server rather than exposing a local stdio server over HTTP. Verify the direction before using any bridge tool.

#### Bridge options

##### Option 1: supergateway (recommended)

[`supergateway`](https://github.com/supercorp-ai/supergateway) is a community-maintained open source tool by [Supercorp AI](https://github.com/supercorp-ai) that runs a stdio MCP server over SSE or Streamable HTTP with a single command. No global install needed — `npx` runs it directly.

```bash
# Expose netmiko-mcp as an SSE endpoint on port 8787
npx -y supergateway --stdio "uv run netmiko-mcp" --outputTransport sse --port 8787

# With a custom config file location:
npx -y supergateway \
  --stdio "NETMIKO_MCP_CONFIG=/path/to/.netmiko-mcp.yml uv run netmiko-mcp" \
  --outputTransport sse --port 8787
```

The bridge listens at `http://localhost:8787/sse`.

To use Streamable HTTP instead of SSE (preferred if ChatGPT supports it — check current OpenAI connector docs):

```bash
npx -y supergateway --stdio "uv run netmiko-mcp" --outputTransport streamableHttp --port 8787
```

##### Option 2: OpenAI Secure MCP Tunnel

OpenAI provides its own [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) — an outbound-only relay where a local tunnel client pulls requests from OpenAI and forwards them to your stdio server without exposing a public port. This is the most secure option as no inbound port needs to be opened. See OpenAI's documentation for setup steps.

##### Option 3: MCP Gateway (Docker)

An MCP gateway runs as a Docker container and handles stdio-to-HTTP translation at the infrastructure level. Heavier to set up but suitable for shared or persistent deployments. See [Apigene's MCP Gateway guide](https://apigene.ai/blog/deploy-mcp-gateway-docker-5-minutes) for a walkthrough.

##### Option 4: Rebuild as a Streamable HTTP server

The cleanest long-term solution is to add native Streamable HTTP transport to `netmiko-mcp` directly, removing the need for any bridge. This is a server-side change out of scope for this guide but worth considering for production deployments.


#### ngrok for HTTPS

`supergateway` exposes HTTP only. Clients that require HTTPS (Perplexity, and potentially others) need ngrok to add a public HTTPS tunnel on top.


[ngrok](https://ngrok.com) is the lowest-friction way to test whether Perplexity's HTTPS requirement can be satisfied. It creates a public HTTPS tunnel to your local `supergateway` endpoint in seconds, with no certificate setup required. A free ngrok account is sufficient for testing.

**Step 1 — Install ngrok**

macOS:
```bash
brew install ngrok
```

Windows:
```bash
winget install ngrok -s msstore
```

Linux (Debian/Ubuntu):
```bash
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
  | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
  && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
  | sudo tee /etc/apt/sources.list.d/ngrok.list \
  && sudo apt update && sudo apt install ngrok
```

**Step 2 — Authenticate ngrok** (one-time setup, free account at [ngrok.com](https://ngrok.com)):

```bash
ngrok config add-authtoken YOUR_TOKEN
```

**Step 3 — Start the bridge and tunnel in two terminals**

Terminal 1 — start supergateway:
```bash
NETMIKO_MCP_CONFIG="/path/to/.netmiko-mcp.yml" \
  npx -y supergateway --stdio "uv run netmiko-mcp" --outputTransport sse --port 8787
```

Terminal 2 — expose it over HTTPS:
```bash
ngrok http 8787
```

ngrok will display a public HTTPS URL like `https://abc123.ngrok-free.app`. Use that URL as the connector endpoint in Perplexity's **Customize → Add Connector** settings.

**What to verify:** Whether Perplexity successfully connects, loads the tool list, and can execute a `ping` or `list devices` call. Update this section with results.

## Secrets

Device credentials (usernames, passwords, enable secrets) must reach Netmiko at connection time, but they should never appear in plaintext in a file that could be committed to version control, shared, or logged.

### What Does Not Work: Environment Variables in the YAML File

A common instinct is to write something like this in `.netmiko.yml`:

```yaml
core01:
  device_type: cisco_ios
  host: 192.168.1.1
  username: admin
  password: "${CORE01_PASSWORD}"
```

This does not work. Netmiko reads the inventory file with Python's `yaml.safe_load()`, which parses values literally. The string `"${CORE01_PASSWORD}"` is passed directly to Netmiko's `ConnectHandler` as the password and the connection will fail. There is no built-in environment variable interpolation.

### Option 1: Netmiko's Built-In Encryption

Netmiko provides a native encryption mechanism. Device passwords in `~/.netmiko.yml` — the device inventory file, not the MCP config — are replaced with `__encrypt__` ciphertext strings. The only secret you need to protect is a passphrase stored in an environment variable called `NETMIKO_TOOLS_KEY`. The encrypted inventory file itself can be shared or committed to version control safely.

Encryption uses [Fernet](https://cryptography.io/en/latest/fernet/) symmetric encryption by default.

#### Step-by-step walkthrough

**Step 1 — Start with a plaintext inventory**

Create `~/.netmiko.yml` with your devices and plaintext passwords. You must include the `__meta__` block — it tells Netmiko how to treat the file.

```yaml
---
__meta__:
  encryption: false
  encryption_type: fernet

core01:
  device_type: arista_eos
  host: 192.168.1.1
  port: 22
  username: admin
  password: plaintext_password_here
  secret: plaintext_enable_secret_here

access01:
  device_type: arista_eos
  host: 192.168.1.2
  port: 22
  username: admin
  password: plaintext_password_here
```

**Step 2 — Choose a passphrase and set the environment variable**

Your passphrase is the master key that protects all device passwords. Anyone with it can decrypt all your credentials — choose something strong.

```bash
export NETMIKO_TOOLS_KEY="some long and strong passphrase"
```

This sets the variable for the current terminal session only. To make it permanent, add it to your shell's startup file:

On macOS/Linux with **zsh** (default on modern macOS):

```bash
echo 'export NETMIKO_TOOLS_KEY="some long and strong passphrase"' >> ~/.zshrc
source ~/.zshrc
```

On macOS/Linux with **bash**:

```bash
echo 'export NETMIKO_TOOLS_KEY="some long and strong passphrase"' >> ~/.bashrc
source ~/.bashrc
```

Verify it is set:

```bash
echo $NETMIKO_TOOLS_KEY
```

If the output is blank, the variable is not set.

**Step 3 — Encrypt the inventory file**

`netmiko-bulk-encrypt` reads your plaintext `~/.netmiko.yml`, encrypts every `password` and `secret` field, and by default writes the result to stdout. Write to a separate file first so you can verify before overwriting the original.

```bash
# Write encrypted output to a temporary file
uv run netmiko-bulk-encrypt --input_file ~/.netmiko.yml --output_file ~/.netmiko_encrypted.yml

# Review the output
cat ~/.netmiko_encrypted.yml

# If it looks correct, replace the original
cp ~/.netmiko_encrypted.yml ~/.netmiko.yml
rm ~/.netmiko_encrypted.yml
```

> **Warning:** Do not use the same path for both `--input_file` and `--output_file`. Always write to a separate file first, verify, then replace.

**Step 4 — Update the `__meta__` block manually**

`netmiko-bulk-encrypt` encrypts the credential values but does **not** automatically change `encryption: false` to `encryption: true`. You must do this yourself. If you skip this step, Netmiko treats the `__encrypt__` strings as literal passwords and all device connections will fail.

Open `~/.netmiko.yml` and change:

```yaml
__meta__:
  encryption: false
```

to:

```yaml
__meta__:
  encryption: true
```

**Step 5 — Verify the encrypted file**

After editing, `~/.netmiko.yml` should look like this:

```yaml
---
__meta__:
  encryption: true
  encryption_type: fernet

core01:
  device_type: arista_eos
  host: 192.168.1.1
  port: 22
  username: admin
  password:
    __encrypt__abc123...:gAAAAA...long_ciphertext...
  secret:
    __encrypt__xyz789...:gAAAAA...long_ciphertext...
```

The `__encrypt__` prefix followed by a salt and ciphertext replaces each plaintext credential. The username is left unencrypted — only `password` and `secret` fields are encrypted.

**Step 6 — Test decryption**

Verify Netmiko can read the file and decrypt correctly by listing your devices through the MCP server:

```
list devices
```

If the server returns your device list without error, decryption is working. If you see authentication failures, check that `__meta__` shows `encryption: true` and that `NETMIKO_TOOLS_KEY` matches the passphrase used during encryption.

**Step 7 — Pass the passphrase to your MCP client**

`NETMIKO_TOOLS_KEY` must be available to the process that runs `netmiko-mcp`. For Claude Code it should already be in your shell environment. For clients that manage the server subprocess (Claude Desktop, Cursor, Devin Desktop), add it to the `env` block in the client config:

```json
"env": {
  "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml",
  "NETMIKO_TOOLS_KEY": "some long and strong passphrase"
}
```

#### Encrypting a single password

To encrypt one password and paste it manually into the YAML file:

```bash
uv run netmiko-encrypt "the_password_to_encrypt"
```

Output:

```
Encrypted data: __encrypt__<salt>:<ciphertext>
```

Copy the full `__encrypt__...` string (everything after `Encrypted data: `) and paste it as the value in your YAML file:

```yaml
password:
  __encrypt__abc123...:gAAAAA...long_ciphertext...
```

> **Security note:** Passing a password on the command line may save it in your shell history. To clear it in bash: `history -d $(history 1)`. Using `netmiko-bulk-encrypt` on the whole file avoids this entirely.

#### Trade-offs

- No external dependencies — everything is built into Netmiko
- The passphrase is the single point of protection — if it is lost, encrypted credentials cannot be recovered; you would need to re-encrypt from plaintext
- The passphrase must be distributed to every machine running the server

### Option 2: Generate the Inventory at Startup from a Secrets Manager

Pull credentials from an external secrets store and write `.netmiko.yml` dynamically before starting the server. The on-disk file is ephemeral and never committed.

**Example using the 1Password CLI:**

```bash
#!/bin/bash
# generate-inventory.sh — run before launching netmiko-mcp

op item get "core01" --fields username,password --format json \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
creds = {f['label']: f['value'] for f in d}
print(f'''---
core01:
  device_type: cisco_ios
  host: 192.168.1.1
  username: {creds['username']}
  password: {creds['password']}
''')
" > ~/.netmiko.yml

uv run netmiko-mcp
```

**Example using AWS Secrets Manager:**

```bash
SECRET=$(aws secretsmanager get-secret-value \
  --secret-id netmiko/core01 \
  --query SecretString --output text)

python3 -c "
import json, sys
d = json.loads('''$SECRET''')
print(f'''---
core01:
  device_type: cisco_ios
  host: 192.168.1.1
  username: {d['username']}
  password: {d['password']}
''')
" > ~/.netmiko.yml

uv run netmiko-mcp
```

**Trade-offs:**
- Credentials never touch disk in the long term — the file is regenerated on each launch
- Requires the secrets manager CLI or SDK to be available on the host
- The generated file exists in plaintext on disk for the duration of the server run; ensure `~/.netmiko.yml` has restrictive permissions (`chmod 600`)
- More moving parts to maintain

### Comparison

| | Built-in encryption | Secrets manager |
|---|---|---|
| External dependency | None | Vault / 1Password / AWS / etc. |
| Passphrase / token to protect | `NETMIKO_TOOLS_KEY` | Secrets manager auth token |
| Plaintext on disk | Never | During server runtime only |
| Suitable for version control | Yes (ciphertext safe to commit) | No (generate fresh each launch) |
| Best for | Individual or small team use | Team or production deployments |

### What to Avoid

- **Plaintext passwords in `.netmiko.yml`** — even in a private repo. Repos get cloned, archived, and shared.
- **Hardcoding credentials in MCP client config files** (`.cursor/mcp.json`, `claude_desktop_config.json`) — these files are often synced or backed up.
- **Putting `NETMIKO_TOOLS_KEY` in a `.env` file that is committed** — defeats the purpose of encryption entirely.

---

## Choosing the Right Client

| Use case | Recommended client |
|---|---|
| Development and testing | Claude Code |
| Daily AI-assisted network ops | Claude Desktop or Cursor |
| Team or multi-agent workflows | Devin Desktop (ACP layer) |
| AWS-focused workflows | Kiro (native AWS MCP integration) |
| Existing Copilot user | VS Code + GitHub Copilot (Agent mode) |
| Local LLM / air-gapped | LM Studio |
| ChatGPT user | ChatGPT + supergateway bridge (extra setup required; UI path unverified) |

---

## Sources

**Client installation and configuration**
- [Model Context Protocol (MCP) — Kiro Docs](https://kiro.dev/docs/mcp/)
- [MCP Server Directory — Kiro Docs](https://kiro.dev/docs/mcp/servers/)
- [Introducing Remote MCP Servers — Kiro Blog](https://kiro.dev/blog/introducing-remote-mcp/)
- [Enterprise MCP Governance — Kiro Docs](https://kiro.dev/docs/enterprise/governance/mcp/)
- [MCP Servers in Cursor — Cursor Docs](https://cursor.com/docs/cli/mcp)
- [MCP Servers in Cursor: Setup, Configuration, and Security (2026)](https://www.truefoundry.com/blog/mcp-servers-in-cursor-setup-configuration-and-security-guide)
- [Cursor fails to fall back from Streamable HTTP to SSE — Cursor Forum](https://forum.cursor.com/t/cursor-fails-to-fall-back-from-streamable-http-to-sse-transport-for-remote-mcp-servers/154390)
- [Windsurf Is Now Devin Desktop — ChatForest](https://chatforest.com/builders-log/windsurf-devin-desktop-rebrand-devin-local-acp-builder-guide/)
- [Devin Desktop FAQ](https://docs.devin.ai/desktop/devin-desktop-faq)
- [Windsurf is now Devin Desktop — Devin Blog](https://devin.ai/blog/windsurf-is-now-devin-desktop/)
- [How to Use MCP Servers in ChatGPT](https://www.usecarly.com/blog/chatgpt-mcp/)
- [How to Install an MCP Server in Claude, ChatGPT, Cursor, Windsurf, and VS Code](https://www.usecarly.com/blog/how-to-install-mcp/)
- [Building MCP servers for ChatGPT — OpenAI Docs](https://developers.openai.com/api/docs/mcp)
- [Add and manage MCP servers in VS Code](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
- [MCP configuration for Amazon Q Developer](https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/mcp-ide.html)
- [Zed External Agents](https://zed.dev/docs/ai/external-agents)
- [Zed Streamable HTTP support discussion — GitHub](https://github.com/zed-industries/zed/discussions/29370)
- [MCP servers with Gemini CLI](https://geminicli.com/docs/tools/mcp-server/)
- [Grok Build MCP support — iClarified](https://www.iclarified.com/100870/xai-launches-grok-build-coding-agent-with-parallel-subagents-and-mcp-support)
- [Remote MCP Tools — xAI Docs](https://docs.x.ai/developers/tools/remote-mcp)
- [Using MCP Across AI Platforms — ChatForest](https://chatforest.com/guides/mcp-across-ai-platforms/)
- [PulseMCP client list](https://www.pulsemcp.com/clients)

**Transport protocol and SSE deprecation**
- [MCP Transports — MCP Specification](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [SSE vs Streamable HTTP: Why MCP Switched — Bright Data](https://brightdata.com/blog/ai/sse-vs-streamable-http)
- [MCP SSE Is Deprecated — Chanl Blog](https://www.channel.tel/blog/mcp-sse-to-streamable-http-migration)
- [MCP SSE vs Stdio: Transport Options Explained (2026) — Apigene](https://apigene.ai/blog/mcp-sse-vs-stdio)
- [MCP Transport: stdio vs Streamable HTTP — TrueFoundry](https://www.truefoundry.com/blog/mcp-stdio-vs-streamable-http-enterprise)
- [Why MCP's Move Away from SSE Simplifies Security — Auth0](https://auth0.com/blog/mcp-streamable-http/)


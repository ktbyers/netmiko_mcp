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

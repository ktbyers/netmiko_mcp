---
name: mcp-client-config
description: Configuration reference for connecting MCP clients (Claude Code, Claude Desktop, Cursor, Devin Desktop, VS Code + GitHub Copilot, Kiro) to the netmiko-mcp server. Covers installation, JSON config blocks, per-client gotchas, and credential handling.
---

# netmiko-mcp Client Configuration

## Default File Locations

If these files exist at the default paths, no environment variables or extra client config are needed:

| File | Default path |
|---|---|
| MCP server config | `~/.netmiko-mcp.yml` |
| Device inventory | `~/.netmiko.yml` |
| Commands whitelist | `~/commands.yml` |

Use `NETMIKO_MCP_CONFIG` to point to a non-default config path. Use `NETMIKO_TOOLS_KEY` to pass the inventory decryption passphrase — see `netmiko-tools-yml` skill.

---

## Making the Server Available to All Clients

`uv pip install -e .` puts the executable only in the project's local `.venv`. Claude Code finds it because it runs from the project directory. All other clients (Claude Desktop, Cursor, Devin Desktop, VS Code) launch the subprocess from their own working directory and will fail unless the tool is installed globally.

**Install from PyPI (future):**
```bash
uv tool install netmiko-mcp
```

**Install from a local source checkout:**
```bash
uv tool install -e /path/to/netmiko_mcp
```

**Verify:**
```bash
uv tool list   # netmiko-mcp should appear
```

---

## Verification Status (June 2026)

| Client | Status | Notes |
|---|---|---|
| Claude Code | ✓ Verified | Full end-to-end tested |
| Claude Desktop | ✓ Verified | Full end-to-end tested |
| Cursor | ✓ Verified | Agent mode required |
| Devin Desktop (formerly Windsurf) | ✓ Verified | Agent mode / Cascade required |
| VS Code + GitHub Copilot | ✓ Verified | Free tier sufficient; use "structured data" phrasing for TextFSM |
| Kiro | — Not tested | Instructions based on documentation only |
| ChatGPT | ✗ Not working | Business plan or higher required; HTTP bridge only — see `mcp-http-transport` skill |
| Perplexity | ✗ Not working | OAuth discovery blocker — see `mcp-http-transport` skill |

---

## Client Support Summary (stdio clients)

| Client | stdio | HTTP (Streamable) | Notes |
|---|---|---|---|
| Claude Code (CLI) | ✓ | ✓ | `claude mcp add --transport http <url>` for remote |
| Claude Desktop | ✓ | ✓ | Remote via Custom Connectors; JSON config for stdio |
| Cursor | ✓ | ✓ | Streamable HTTP + SSE fallback (fallback has known bug — pin transport explicitly) |
| Devin Desktop (formerly Windsurf) | ✓ | ✓ | ACP multi-agent layer sits above MCP |
| Kiro (AWS IDE) | ✓ | ✓ | Streamable HTTP + SSE fallback; strong native MCP docs |
| VS Code + GitHub Copilot | ✓ | ✓ | Agent mode only; GA since VS Code 1.102 |
| Cline | ✓ | ✓ | VS Code, JetBrains, Cursor, Zed, Neovim |
| Gemini CLI | ✓ | ✓ | stdio + SSE + Streamable HTTP; OAuth 2.0 for remote |
| Perplexity Mac app | ✓ | — | Local stdio via PerplexityXPC helper |
| ChatGPT | ✗ | ✓ | HTTP bridge required — see `mcp-http-transport` skill |

---

## Claude Code

The simplest client. Recommended for development and testing.

**Basic registration (default config `~/.netmiko-mcp.yml`):**
```bash
# Project scope
claude mcp add netmiko-mcp -- uv run netmiko-mcp

# User scope (available in all projects)
claude mcp add -s user netmiko-mcp -- uv run netmiko-mcp
```

**With a custom config path:**
```bash
claude mcp add -s user \
  -e NETMIKO_MCP_CONFIG="/path/to/.netmiko-mcp.yml" \
  netmiko-mcp -- uv run netmiko-mcp
```

**With encrypted inventory credentials:**
```bash
claude mcp add -s user \
  -e NETMIKO_MCP_CONFIG="/path/to/.netmiko-mcp.yml" \
  -e NETMIKO_TOOLS_KEY="your_passphrase" \
  netmiko-mcp -- uv run netmiko-mcp
```

Claude Code stores env vars in `~/.claude.json` and injects them on every launch — no need to export them in your shell.

**Remove:**
```bash
claude mcp remove netmiko-mcp -s user
```

**Verify:** ask `ping` — should return `pong`.

---

## Claude Desktop

Config file: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows).

**Option 1 — uv tool (recommended):**
Requires `netmiko-mcp` installed as a global uv tool.

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "uv",
      "args": ["run", "netmiko-mcp"],
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml",
        "NETMIKO_TOOLS_KEY": "your_passphrase"
      }
    }
  }
}
```

Omit the `env` block entirely if using default file locations and no encryption.

**Option 2 — absolute path to venv binary:**
Use when not installed as a global tool. Brittle if the repo moves.

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "/path/to/netmiko_mcp/.venv/bin/netmiko-mcp",
      "args": []
    }
  }
}
```

Find the path: `find ~ -path "*netmiko_mcp/.venv/bin/netmiko-mcp" 2>/dev/null`

**Critical gotchas:**
- Claude Desktop silently reverts the config file on any JSON syntax error. Validate JSON before saving: `python3 -m json.tool claude_desktop_config.json`
- Do not edit the file while Claude Desktop is running — it may overwrite changes on exit
- If the server disappears after restart, the config was reverted. Check for the `mcpServers` key
- Server logs: `~/Library/Logs/Claude/mcp*.log` (macOS)
- Tools are **deferred loaded** — not available until the first time Claude needs them. A brief pause on the first tool call is normal
- Restart Claude Desktop after any config change. Go to **Settings → Developer** to verify the server status

---

## Cursor

Config file locations:

| Scope | Path |
|---|---|
| Project | `.cursor/mcp.json` (repo root) |
| Global | `~/.cursor/mcp.json` |

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "uv",
      "args": ["run", "netmiko-mcp"],
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml",
        "NETMIKO_TOOLS_KEY": "your_passphrase"
      }
    }
  }
}
```

**Critical gotchas:**
- **Agent mode is required** for MCP tool calls. Ask mode blocks all tool execution, including `ping`. Switch to Agent mode in the chat input area before making any requests
- If tools appear available but calls are blocked, this is almost always the cause
- Verify the server loaded: **Settings → Tools & MCPs** — active servers show a green indicator
- Run `command` + `args` in a terminal to surface startup errors Cursor may suppress

---

## Devin Desktop (formerly Windsurf)

Windsurf was rebranded as Devin Desktop on June 2, 2026. Existing configs migrate automatically. The `~/.codeium/` directory structure is unchanged.

Config file:

| Platform | Path |
|---|---|
| macOS / Linux | `~/.codeium/windsurf/mcp_config.json` |
| Windows | `%USERPROFILE%\.codeium\windsurf\mcp_config.json` |

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "uv",
      "args": ["run", "netmiko-mcp"],
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml",
        "NETMIKO_TOOLS_KEY": "your_passphrase"
      }
    }
  }
}
```

**Critical gotchas:**
- Switch to **Agent mode (Cascade)** before making requests. The panel is labeled Cascade even after the rebrand
- If the server status isn’t visible in settings, ask Cascade directly — it will confirm whether the tool is available

---

## VS Code + GitHub Copilot

GA since VS Code 1.102. **Free GitHub Copilot tier is sufficient.**

VS Code uses `"servers"` (not `"mcpServers"`) and requires an explicit `"type"` field — unlike every other client.

Config file locations:

| Scope | Path |
|---|---|
| Workspace | `.vscode/mcp.json` (repo root) |
| User | User `settings.json` under `"mcp"` → `"servers"` |

**Workspace scope** — `.vscode/mcp.json`:
```json
{
  "servers": {
    "netmiko-mcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "netmiko-mcp"],
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml",
        "NETMIKO_TOOLS_KEY": "your_passphrase"
      }
    }
  }
}
```

**User scope** — add to `settings.json` (`Cmd+Shift+P` → Open User Settings JSON):
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

**Critical gotchas:**
- Key is `"servers"`, not `"mcpServers"` — wrong key silently does nothing
- `"type": "stdio"` is required — omitting it causes the server to not load
- After editing, reload VS Code: `Cmd+Shift+P` → **Developer: Reload Window**
- Verify: **Command Palette → MCP: List Servers**
- For TextFSM parsing, use the phrase **"structured data"** in prompts — `"in JSON format"` alone often does not trigger `use_textfsm=True`
- Startup errors: **Output panel → GitHub Copilot**

---

## Kiro

AWS IDE with strong native MCP support. See [kiro.dev/docs/mcp/](https://kiro.dev/docs/mcp/) — best MCP docs of any client.

Config file locations:

| Scope | Path |
|---|---|
| Global | `~/.kiro/settings/mcp.json` |
| Project | `.kiro/settings/mcp.json` (repo root) |

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "uv",
      "args": ["run", "netmiko-mcp"],
      "env": {
        "NETMIKO_MCP_CONFIG": "/path/to/.netmiko-mcp.yml",
        "NETMIKO_TOOLS_KEY": "your_passphrase"
      }
    }
  }
}
```

Not end-to-end tested as of June 2026. If the server does not load, Kiro’s MCP settings panel shows status and startup errors.

---

## Choosing the Right Client

| Use case | Recommended client |
|---|---|
| Development and testing | Claude Code |
| Daily AI-assisted network ops | Claude Desktop or Cursor |
| Team or multi-agent workflows | Devin Desktop (ACP layer) |
| AWS-focused workflows | Kiro |
| Existing Copilot user | VS Code + GitHub Copilot (Agent mode) |
| Web GUI (no local install) | Claude.ai with remote HTTP deployment |
| ChatGPT user | ChatGPT + supergateway bridge (extra setup — see `mcp-http-transport` skill) |

---

## Secrets and Credential Management

See the `netmiko-tools-yml` skill for the full inventory encryption walkthrough, secrets manager integration examples, comparison table, and credential best practices.

**Two things that matter when configuring clients:**
- `${ENV_VAR}` interpolation in `.netmiko.yml` does **not** work — Netmiko parses values literally
- Never put `NETMIKO_TOOLS_KEY` or device passwords in client config files (`.cursor/mcp.json`, `claude_desktop_config.json`) — these files are often synced or backed up

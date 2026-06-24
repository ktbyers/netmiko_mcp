---
name: mcp-client-config
description: Configuration reference for connecting MCP clients (Claude Code, Claude Desktop, Cursor, Devin Desktop, VS Code + GitHub Copilot, Kiro) to the netmiko-mcp server. Covers installation, JSON config blocks, per-client gotchas, and credential handling.
---

> **For humans:** This file is reference documentation for connecting MCP clients to the netmiko-mcp server. You can read it directly, but its real purpose is to be installed as a skill in your AI client — once loaded into Claude's context, you can ask it to generate the exact config block for your client and it already has the JSON, the gotchas, and the known bugs. See the [Claude Code Skills](../../README.md#claude-code-skills) section in the README for installation instructions.

# netmiko-mcp Client Configuration

## Default File Locations

| File | Default path |
|---|---|
| MCP server config | `~/.netmiko-mcp.yml` |
| Device inventory | `~/.netmiko.yml` |
| Commands whitelist | `~/commands.yml` |

Use `NETMIKO_MCP_CONFIG` to point to a non-default config path. Use `NETMIKO_TOOLS_KEY` to pass the inventory decryption passphrase — see `netmiko-tools-yml` skill.

---

## Making the Server Available to All Clients

All clients except Claude Code launch the server from their own working directory and require a global installation. `uv pip install -e .` only installs into the project's local `.venv`.

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

## Claude Code

**Basic registration (default config `~/.netmiko-mcp.yml`):**
```bash
# Project scope
claude mcp add netmiko-mcp -- uv run netmiko-mcp

# User scope (available in all projects)
claude mcp add -s user netmiko-mcp -- uv run netmiko-mcp
```

**User scope with source install (`uv sync`, not `uv tool install`):**
`uv run netmiko-mcp` only works when Claude Code is invoked from the repo directory.
For user scope, where Claude Code may be invoked from any directory, use `--directory`
to pin the project root:

```bash
claude mcp add -s user \
  -e NETMIKO_MCP_CONFIG="/abs/path/to/repo/.netmiko-mcp.yml" \
  netmiko-mcp -- uv run --directory /abs/path/to/repo netmiko-mcp
```

`-e NETMIKO_MCP_CONFIG` is required here — without it the server falls back to
home-dir discovery and may fail at startup if `~/commands.yml` does not exist.

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

**Option 3 — remote HTTP server via mcp-remote bridge:**
Claude Desktop has no native plain-bearer HTTP support and crashes if a `headers` block is included in the config. Use `mcp-remote` (Node.js required) as a local stdio-to-HTTP bridge.

Two bugs to work around:
- **Header space-splitting:** passing `--header "Authorization: Bearer <token>"` fragments at the space and breaks auth. Put `Bearer <token>` in the `env` block and reference it via `Authorization:${VAR}` with no space after the colon.
- **SSE probe:** mcp-remote probes SSE first by default, which hangs or returns 405 against a streamable-HTTP-only server. Pass `--transport` and `http-only` as separate args to skip the probe.

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://your-mcp-server.example.com/mcp",
        "--transport",
        "http-only",
        "--header",
        "Authorization:${NETMIKO_MCP_HTTP_BEARER_TOKEN}"
      ],
      "env": {
        "NETMIKO_MCP_HTTP_BEARER_TOKEN": "Bearer your-token-here"
      }
    }
  }
}
```

Checklist:
- `--transport` and `http-only` must be separate array elements — not a single `"--transport http-only"` string
- `Authorization:${NETMIKO_MCP_HTTP_BEARER_TOKEN}` must have no spaces around the colon
- The `env` value must include the literal word `Bearer` followed by a space and the token

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

- Key is `"servers"`, not `"mcpServers"` — wrong key silently does nothing
- `"type": "stdio"` is required — omitting it causes the server to not load
- After editing, reload VS Code: `Cmd+Shift+P` → **Developer: Reload Window**
- Verify: **Command Palette → MCP: List Servers**
- For TextFSM parsing, use the phrase **"structured data"** in prompts — `"in JSON format"` alone often does not trigger `use_textfsm=True`
- Startup errors: **Output panel → GitHub Copilot**

---

## Kiro

See [kiro.dev/docs/mcp/](https://kiro.dev/docs/mcp/) for official Kiro MCP configuration docs.

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

## Secrets and Credential Management

See the `netmiko-tools-yml` skill for the full inventory encryption walkthrough, secrets manager integration examples, comparison table, and credential best practices.

- `${ENV_VAR}` interpolation in `.netmiko.yml` does **not** work — Netmiko parses values literally
- Never put `NETMIKO_TOOLS_KEY` or device passwords in client config files (`.cursor/mcp.json`, `claude_desktop_config.json`) — these files are often synced or backed up

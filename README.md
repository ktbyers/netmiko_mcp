# Netmiko MCP Server

> **⚠️ WARNING:** You can make serious, incredibly detrimental mistakes by using this tool. This tool could cause massive outages in your environment. You, and you alone, are solely responsible for using this tool. Don't say I didn't warn you.

> I have tried to make reasonable defaults and to limit what the Netmiko-MCP server allows (by default). It is highly advisable to start with ONLY show commands executed against ONLY test or lab devices. You should also strongly consider additional security mechanisms completely outside of the LLM and Netmiko- MCP (for example, a tightly-controlled AAA solution). LLMs and LLM-agents inherently have a lot of variance and are difficult to predict and control.


## Getting Started

Setup requires three things: an MCP configuration file, a device inventory, and a commands whitelist.

First, set the `NETMIKO_MCP_CONFIG` environment variable to point at the configuration file you are about to create:

```
export NETMIKO_MCP_CONFIG=~/.netmiko-mcp.yml
```

### Step 1 — Create the MCP configuration file

Create `~/.netmiko-mcp.yml`:

```yaml
---
inventory_type: "netmiko_tools"
inventory_file: "~/.netmiko.yml"
command_file: "~/commands.yml"
```

Full details on every setting and its environment variable override: [docs/configuration.md](docs/configuration.md)

### Step 2 — Create the device inventory

Create `~/.netmiko.yml` containing your devices and encrypted credentials. The inventory
format is documented [here](https://pynet.twb-tech.com/blog/netmiko-grep-command-line-utility.html#creating-the-inventory).
There is also an AI [skill file](https://github.com/ktbyers/netmiko_mcp/blob/main/skills/netmiko-tools-yml/SKILL.md)
available for assistance.

### Step 3 — Create the commands whitelist

Create `~/commands.yml` to define what the LLM is allowed to send to devices. By default
**no commands are permitted**:

```yaml
---
allowed_commands:
  - "show version"
  - "show ip interface brief"

denied_commands: []
```

Full details on allowed/denied matching, globbing, pipes, and unsafe characters: [docs/commands.md](docs/commands.md)

### Step 4 — Register with your MCP client

Add the server to your MCP client configuration (e.g. Claude Code or Claude Desktop).
Set `NETMIKO_MCP_CONFIG` and `NETMIKO_TOOLS_KEY` in the client's `env` block:

```json
{
  "mcpServers": {
    "netmiko-mcp": {
      "command": "netmiko-mcp",
      "env": {
        "NETMIKO_MCP_CONFIG": "/Users/yourname/.netmiko-mcp.yml",
        "NETMIKO_TOOLS_KEY": "<your-decryption-key>"
      }
    }
  }
}
```

---

## Documentation

| Document | Description |
|---|---|
| [docs/configuration.md](docs/configuration.md) | Full reference for `~/.netmiko-mcp.yml` — all settings, defaults, and env var overrides |
| [docs/commands.md](docs/commands.md) | Full reference for `commands.yml` — allowed/denied matching, globbing, pipes, unsafe characters, and examples |

---

## MCP Tools

The server exposes three tools to MCP clients:

| Tool | Description |
|---|---|
| `send_show_command` | Connect to a device and execute a show command. Accepts `device_name`, `command`, and optional `use_textfsm=True` to return structured JSON instead of raw text. |
| `list_devices` | List devices from the inventory. Accepts an optional `device_or_group` argument (defaults to `"all"`). Credentials are never included in the response. |
| `ping` | Health check. Returns `"pong"`. |

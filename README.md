# Netmiko MCP Server

> **WARNING:** You can make serious, incredibly detrimental mistakes by using this tool. This tool could cause massive outages in your environment. You, and you alone, are solely responsible for using this tool. Don't say I didn't warn you.

> I have tried to make reasonable defaults and to limit what the Netmiko-MCP server allows (by default). It is highly advisable to start with ONLY show commands executed against ONLY test or lab devices. You should also strongly consider additional security mechanisms completely outside of the LLM and Netmiko- MCP (for example, a tightly-controlled AAA solution). LLMs and LLM-agents inherently have a lot of variance and are difficult to predict and control.
<br />

## Getting Started

Setup requires three things: an MCP configuration file, a device inventory, and a commands whitelist.

First, set the `NETMIKO_MCP_CONFIG` environment variable to point at the configuration file you are about to create. Add the following line to your shell's initialization file (`~/.bashrc` (bash) or `~/.zshrc` (zsh)

```bash
export NETMIKO_MCP_CONFIG="$HOME/.netmiko-mcp.yml"
```
<br />

### Step 1 — Create the Netmiko-MCP configuration file

Create `~/.netmiko-mcp.yml`:

```yaml
---
inventory_type: "netmiko_tools"
inventory_file: "~/.netmiko.yml"
command_file: "~/commands.yml"
```

Additional details on the Netmiko-MCP configuration file and corresponding environment variables: [docs/configuration.md](docs/configuration.md)
<br />

### Step 2 — Create the device inventory

Currently, device inventory is limited to Netmiko Tools' [device inventory](https://pynet.twb-tech.com/blog/netmiko-grep-command-line-utility.html#creating-the-inventory). It is likely this will be expanded in the future to support additional inventory sources.

Create the `~/.netmiko.yml` device inventory. This file contains device dictionaries and groups of devices. It also supports encryption for keys and secrets.

Netmiko Tools AI [skill file](https://github.com/ktbyers/netmiko_mcp/blob/main/skills/netmiko-tools-yml/SKILL.md)
<br />

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
<br />

## Reference Documentation

| Document | Description |
|---|---|
| [docs/configuration.md](docs/configuration.md) | Netmiko-MCP configuration file settings |
| [docs/commands.md](docs/commands.md) | Netmiko-MCP allowed commands, denied commands |
<br />


## MCP Tools

The server exposes three tools to MCP clients:

| Tool | Description |
|---|---|
| `send_show_command` | Connect to a device and execute a show command. Accepts `device_name`, `command`, and optional `use_textfsm=True` to return structured JSON instead of raw text. |
| `list_devices` | List devices from the inventory. Accepts an optional `device_or_group` argument (defaults to `"all"`). Credentials are never included in the response. |
| `ping` | Health check. Returns `"pong"`. |

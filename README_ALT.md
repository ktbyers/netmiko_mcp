# Netmiko MCP Server

> **WARNING:** You can make serious, incredibly detrimental mistakes by using this tool. This tool could cause massive outages in your environment. You, and you alone, are solely responsible for using this tool. Don't say I didn't warn you.

> I have tried to make reasonable defaults and to limit what the Netmiko-MCP server allows (by default). It is highly advisable to start with ONLY show commands executed against ONLY test or lab devices. You should also strongly consider additional security mechanisms completely outside of the LLM and Netmiko- MCP (for example, a tightly-controlled AAA solution). LLMs and LLM-agents inherently have a lot of variance and are difficult to predict and control.
<br />

## How This Works

`netmiko-mcp` is a **local stdio server**. It does not run as a standalone service or daemon rather your AI client launches it as a subprocess either at startup or on demand and communicates with it over standard input/output. The server process starts when you open a session and stops when you close it. No ports are opened; nothing listens on the network.

This means two things for setup:

1. **The server must be installed on the same machine as your AI client.** It cannot be installed on a remote host and shared across machines unless you add an HTTP proxy layer.
2. **Your AI client needs to know how to launch it.** Each client has its own config file where you register the server command. The client handles starting and stopping the process automatically either at AI client startup or when you ask a relevant question like "Can you ping the Netmiko MCP server?"

---

## Installation

Install using `uv`:

```bash
uv tool install netmiko-mcp
```

Or install from source:

```bash
git clone https://github.com/ktbyers/netmiko_mcp
cd netmiko_mcp
uv pip install -e .
```

> **Note:** `uv pip install -e .` installs into the project's local virtual environment, which works for Claude Code but not for clients like Claude Desktop, Cursor, Devin (formerly Windsurf) that launch the server from a different working directory. See [docs/mcp_ai_client_installation_guide.md](docs/mcp_ai_client_installation_guide.md) for details on making the server available globally.

---

## Getting Started

Setup requires three things: an MCP configuration file, a device inventory, and a commands whitelist.

> **Simplest setup:** Place all three files in your home directory using the default names:  `~/.netmiko-mcp.yml`, `~/.netmiko.yml`, and `~/commands.yml`. The server finds them automatically with no environment variables or extra configuration required in any client.

If you need to use different locations, set the `NETMIKO_MCP_CONFIG` environment variable to point at your configuration file which can point to custom locations for your inventory and command YML files:

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
<br />

### Step 2 — Create the device inventory

Currently, device inventory is limited to Netmiko Tools' [device inventory](https://pynet.twb-tech.com/blog/netmiko-grep-command-line-utility.html#creating-the-inventory). It is likely this will be expanded in the future to support additional inventory sources.

Create the `~/.netmiko.yml` device inventory. This file contains device dictionaries and groups of devices.

**A note on credentials:** The Netmiko Tools inventory format requires that device usernames and passwords be stored in this file. Plaintext credentials are perfectly fine for lab or test environments. For anything beyond that, it is strongly recommended to use the built-in encryption option.  Netmiko can encrypt the credential fields so the file can be stored safely without exposing passwords in cleartext. See the [Secrets](docs/mcp_ai_client_installation_guide.md#secrets) section of the installation guide for details on both plaintext and encrypted approaches.

Netmiko Tools AI [skill file](https://github.com/ktbyers/netmiko_mcp/blob/main/skills/netmiko-tools-yml/SKILL.md)
<br />
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

The default location is `~/commands.yml`. To use a different path, set `command_file` in your `~/.netmiko-mcp.yml`:

```yaml
command_file: "~/network/commands.yml"
```

Or override it with an environment variable:

```bash
export NETMIKO_MCP_COMMAND_FILE="~/network/commands.yml"
```

Full details on allowed/denied matching, globbing, pipes, and unsafe characters: [docs/commands.md](docs/commands.md)
<br />
<br />

## Registering with Your AI Client

With the server installed and the three config files in place, register `netmiko-mcp` with your AI client. The client needs to know the command to launch the server.  It handles starting and stopping the process automatically.

**Claude Code**

The local/user scope system is specific to Claude Code.  Other clients handle scope by which config file you edit rather than a command flag.

Claude Code supports two registration scopes:

| Scope | Flag | Available in | Config location |
|---|---|---|---|
| **Local** | _(default)_ | This project/directory only | `~/.claude.json` (project entry) |
| **User** | `-s user` | All your projects | `~/.claude.json` (user entry) |

Register for the current project only (recommended when testing or if different projects need different configs). These two commands are equivalent — `-s local` is the default:

```bash
claude mcp add netmiko-mcp -- uv run netmiko-mcp
claude mcp add -s local netmiko-mcp -- uv run netmiko-mcp
```

Register for all your projects:

```bash
claude mcp add -s user netmiko-mcp -- uv run netmiko-mcp
```

To remove:

```bash
# Remove local (project-scoped) registration
claude mcp remove netmiko-mcp -s local

# Remove user (global) registration
claude mcp remove netmiko-mcp -s user
```

Verify it is running by asking Claude to ping the server — it should respond `pong`.

If your `netmiko-mcp.yml` is not at the default location (`~/.netmiko-mcp.yml`), you will need to tell each client where to find it. Each client handles this differently — see [docs/mcp_ai_client_installation_guide.md](docs/mcp_ai_client_installation_guide.md) for per-client instructions including config file locations, env var injection, and installation steps.

---

## Reference Documentation

| Document | Description |
|---|---|
| [docs/configuration.md](docs/configuration.md) | Netmiko-MCP configuration file settings |
| [docs/commands.md](docs/commands.md) | Netmiko-MCP allowed commands, denied commands |
| [docs/mcp_ai_client_installation_guide.md](docs/mcp_ai_client_installation_guide.md) | AI client installation guide (Claude Code, Claude Desktop, Cursor, Devin Desktop, ChatGPT, and more) |
<br />


## MCP Tools

The server exposes three tools to MCP clients:

| Tool | Description |
|---|---|
| `send_show_command` | Connect to a device and execute a show command. Accepts `device_name`, `command`, and optional `use_textfsm=True` to return structured JSON instead of raw text. |
| `list_devices` | List devices from the inventory. Accepts an optional `device_or_group` argument (defaults to `"all"`). Credentials are never included in the response. |
| `ping` | Health check. Returns `"pong"`. |

---

## Usage Examples

### Human-readable table output

> **Prompt:** Execute show version on all the switches configured for my NetMiko MCP server

The LLM discovers devices via `list_devices`, runs `show version` on each in parallel, and formats the results as a table:

| Field | core01 | access01 |
|-------|--------|----------|
| Platform | Arista cEOSLab | Arista cEOSLab |
| EOS Version | 4.35.2F (engineering build) | 4.35.2F (engineering build) |
| Architecture | x86_64 | x86_64 |
| Kernel | 5.15.0-181-generic | 5.15.0-181-generic |
| Serial | 34142FDC416C66E78611C8DF0D03306C | B1AFD6AA33B7A826E56244D42BBD9B8C |
| System MAC | 001c.7395.64b0 | 001c.7333.16be |
| Uptime | 1d 22h 15m | 1d 22h 15m |
| Total Memory | ~16 GB | ~16 GB |
| Free Memory | ~12.2 GB | ~12.2 GB |

---

### Structured JSON output

> **Prompt:** Execute show version on all the switches configured for my NetMiko MCP server and return the data in JSON format.

Adding "in JSON format" to your prompt causes the LLM to invoke `send_show_command` with `use_textfsm=True`, which parses the raw output into structured data via ntc-templates:

```json
{
  "core01": {
    "model": "cEOSLab",
    "hw_version": "",
    "serial_number": "34142FDC416C66E78611C8DF0D03306C",
    "sys_mac": "001c.7395.64b0",
    "image": "4.35.2F-46221466.4352F",
    "total_memory": "16336752",
    "free_memory": "12870640",
    "uptime": "1 day, 22 hours and 16 minutes"
  },
  "access01": {
    "model": "cEOSLab",
    "hw_version": "",
    "serial_number": "B1AFD6AA33B7A826E56244D42BBD9B8C",
    "sys_mac": "001c.7333.16be",
    "image": "4.35.2F-46221466.4352F",
    "total_memory": "16336752",
    "free_memory": "12876236",
    "uptime": "1 day, 22 hours and 16 minutes"
  }
}
```

The structured output is useful when you want to pipe results into another tool, compare fields programmatically, or ask the LLM follow-up questions that require field-level access (e.g., "which devices are running a version older than 4.34?").

---

### Saving output to local files

> **Prompt:** Run `show version` on every device in my NetMiko MCP inventory, return structured JSON, and save each device's output to a file named `<device-name>.json` in my current directory.

The LLM will collect results for all devices and write one file per device. Being explicit about the filename convention (`<device-name>.json`) and the target location (`current directory`) prevents it from guessing.

> **Tip:** If you omit the directory, the LLM will save files relative to whatever working directory your AI client is running from — which may not be where you expect. Specify an absolute path (e.g., `~/network/output/`) if you want the files in a particular location.

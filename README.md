# Netmiko MCP Server

> **WARNING:** You can make serious, incredibly detrimental mistakes by using this tool. This tool could cause massive outages in your environment. You, and you alone, are solely responsible for using this tool. Don't say I didn't warn you.

> I have tried to make reasonable defaults and to limit what the Netmiko-MCP server allows (by default). It is highly advisable to start with ONLY show commands executed against ONLY test or lab devices. You should also strongly consider additional security mechanisms completely outside of the LLM and Netmiko- MCP (for example, a tightly-controlled AAA solution). LLMs and LLM-agents inherently have a lot of variance and are difficult to predict and control.
<br />

## Security Recommendations

The controls in Netmiko-MCP are a best-effort layer and should not be your only line of defense. You should strongly consider using AAA (e.g. TACACS+) with a dedicated read-only service account. AAA should independently authorize and audit what commands the account can execute on your devices. The MCP command authorization can potentially be bypassed, so this tool should only be used by authorized personnel. Untrusted input should not be used with this MCP.
<br />
<br />

## How This Works

`netmiko-mcp` supports two transport modes:

**stdio** - Your AI client launches the server as a local subprocess and communicates over standard input/output. No ports are opened and nothing listens on the network. The process starts when you open a session and stops when you close it. This is the simplest setup and the right choice for a single user running the server on their own machine.

**Streamable HTTP** - The server runs as a standalone service that listens on a network port. Your AI client connects to it over HTTP rather than launching it as a subprocess. This allows the server to run on a remote host and be shared across multiple machines or clients. It also enables centralized control and auditing/logging of all device interactions in one place. The tradeoff is a slightly more involved deployment (you are responsible for starting the process and keeping it running).


## Installation

Install using `uv`:

```bash
uv tool install netmiko-mcp
```

Or install from source:

```bash
git clone https://github.com/ktbyers/netmiko_mcp
cd netmiko_mcp
uv sync
```

> **Note:** `uv sync` installs into the project's local virtual environment, which works for Claude Code but not for clients like Claude Desktop, Cursor, Devin (formerly Windsurf) that launch the server from a different working directory.


## Getting Started

Setup requires three things: an MCP configuration file, a device inventory, and a commands whitelist.

> **Simplest setup:** Place all three files in your home directory using the default names:  `~/.netmiko-mcp.yml`, `~/.netmiko.yml`, and `~/commands.yml`. The server finds them automatically with no environment variables or extra configuration required in any client.

If you need to use different locations, set the `NETMIKO_MCP_CONFIG` environment variable to point at your configuration file which can point to custom locations for your inventory and command YML files:

```bash
export NETMIKO_MCP_CONFIG="$HOME/.netmiko-mcp.yml"
```
<br />

### Step 1 - Create the Netmiko-MCP configuration file

Create `~/.netmiko-mcp.yml`:

```yaml
inventory_type: "netmiko_tools"
inventory_file: "~/.netmiko.yml"
command_file: "~/commands.yml"
```

Additional details on the Netmiko-MCP configuration file and corresponding environment variables: [docs/configuration.md](docs/configuration.md)
<br />
<br />

### Step 2 - Create the device inventory

Currently, device inventory is limited to Netmiko Tools' [device inventory](https://pynet.twb-tech.com/blog/netmiko-grep-command-line-utility.html#creating-the-inventory). It is likely this will be expanded in the future to support additional inventory sources.

Create the `~/.netmiko.yml` device inventory. This file contains device dictionaries and groups of devices.

**A note on credentials:** The Netmiko Tools inventory format requires that device usernames and passwords be stored in this file. Plaintext credentials are perfectly fine for lab or test environments. For anything beyond that, it is strongly recommended to use the built-in encryption option.  Netmiko can encrypt the credential fields so the file can be stored safely without exposing passwords in cleartext. See the [netmiko-tools-yml skill](skills/netmiko-tools-yml/SKILL.md) for details on both plaintext and encrypted approaches.

Netmiko Tools AI [skill file](https://github.com/ktbyers/netmiko_mcp/blob/main/skills/netmiko-tools-yml/SKILL.md)
<br />
<br />

### Step 3 - Create the commands whitelist

Create `~/commands.yml` to define what the LLM is allowed to send to devices. By default
**no commands are permitted**:

```yaml
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

Full details on allowed/denied matching, globbing, pipes, and allowed characters: [docs/commands.md](docs/commands.md)
<br />
<br />

## Registering with Your AI Client

With the server installed and the three config files in place, register `netmiko-mcp` with your AI client. Each client has its own config file or CLI command for registering the server - see the [mcp-client-config skill](skills/mcp-client-config/SKILL.md) for per-client instructions covering Claude Code, Claude Desktop, Cursor, Devin Desktop, VS Code + GitHub Copilot, and Kiro.


## Supported MCP Clients (June 2026)

| Client | stdio | HTTP | Verified | Notes |
|---|---|---|---|---|
| Claude Code | ✓ | ✓ | ✓ | Recommended for development and testing |
| Claude Desktop | ✓ | ✓ | ✓ | Agent mode; deferred tool loading |
| Cursor | ✓ | ✓ | ✓ | Agent mode required; HTTP SSE fallback has known bug |
| Devin Desktop (formerly Windsurf) | ✓ | ✓ | ✓ | Agent mode (Cascade) required |
| VS Code + GitHub Copilot | ✓ | ✓ | ✓ | Agent mode only; free tier sufficient |
| Kiro (AWS IDE) | ✓ | ✓ | - | Not tested; based on documentation |
| Cline | ✓ | ✓ | - | Not tested |
| Gemini CLI | ✓ | ✓ | - | Not tested |
| Perplexity Mac app | ✓ | - | - | stdio via PerplexityXPC helper |
| ChatGPT | ✗ | ✓ | ✗ | Business plan required; HTTP bridge needed; not working |
| Perplexity web | ✗ | ✓ | ✗ | OAuth 2.1 discovery required; not working |
<br />


## Reference Documentation

| Document | Description |
|---|---|
| [docs/configuration.md](docs/configuration.md) | Netmiko-MCP configuration file settings |
| [docs/commands.md](docs/commands.md) | Netmiko-MCP allowed commands, denied commands |
| [skills/mcp-client-config/SKILL.md](skills/mcp-client-config/SKILL.md) | Per-client MCP configuration (Claude Code, Claude Desktop, Cursor, Devin Desktop, VS Code, Kiro) |
| [skills/netmiko-tools-yml/SKILL.md](skills/netmiko-tools-yml/SKILL.md) | Device inventory format, credential encryption, secrets manager integration |
<br />


## MCP Tools

The server exposes seven tools to MCP clients:

| Tool | Description |
|---|---|
| `send_show_command` | Connect to a single device and execute a show command. Accepts `device_name`, `command`, and optional `use_textfsm=True` to return structured JSON instead of raw text. |
| `send_show_command_to_group` | Execute a show command concurrently across a device group. Accepts `device_or_group`, `command`, optional `use_textfsm=True`, and optional `save_output=True` to write per-device files instead of returning raw output. |
| `list_devices` | List devices from the inventory. Accepts an optional `device_or_group` argument (defaults to `"all"`). Credentials are never included in the response. |
| `list_groups` | List all device group names defined in the inventory. Returns a list of strings. |
| `list_device_outputs` | List saved output files for a device, group, or `"all"`. Returns a dict mapping device names to lists of saved filenames (newest first). |
| `read_device_output` | Read a previously saved output file. Accepts `device_name` and `filename` (as returned by `list_device_outputs`). |
| `ping` | Health check. Returns `"pong"`. |


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


### Saving output to local files

> **Prompt:** Run `show version` on every device in my NetMiko MCP inventory, return structured JSON, and save each device's output to a file named `<device-name>.json` in my current directory.

The LLM will collect results for all devices and write one file per device. Being explicit about the filename convention (`<device-name>.json`) and the target location (`current directory`) prevents it from guessing.

> **Tip:** If you omit the directory, the LLM will save files relative to whatever working directory your AI client is running from - which may not be where you expect. Specify an absolute path (e.g., `~/network/output/`) if you want the files in a particular location.
